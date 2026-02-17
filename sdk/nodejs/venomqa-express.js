/**
 * VenomQA Express Middleware
 *
 * Implements the VenomQA Control Protocol for Express.js applications.
 * Allows VenomQA to manage database transactions for state exploration testing.
 *
 * Usage:
 *   const { venomqaMiddleware, venomqaRouter } = require('@venomqa/express');
 *
 *   // Add middleware to inject VenomQA-controlled connections
 *   app.use(venomqaMiddleware(pool));
 *
 *   // Add control endpoints (only in test mode!)
 *   if (process.env.VENOMQA_ENABLED === 'true') {
 *     app.use('/venomqa', venomqaRouter(pool));
 *   }
 */

const express = require('express');

// Active VenomQA sessions: sessionId -> { connection, checkpoints }
const sessions = new Map();

/**
 * Creates the VenomQA control router.
 *
 * @param {Pool} pool - PostgreSQL pool (pg library)
 * @returns {Router} Express router with control endpoints
 */
function venomqaRouter(pool) {
  const router = express.Router();
  router.use(express.json());

  // Health check
  router.get('/health', (req, res) => {
    res.json({
      status: 'ok',
      venomqa_protocol: '1.0',
      database: 'postgresql',
      active_sessions: sessions.size,
    });
  });

  // Begin session
  router.post('/begin', async (req, res) => {
    const { session_id } = req.body;

    if (!session_id) {
      return res.status(400).json({ error: 'session_id required' });
    }

    if (sessions.has(session_id)) {
      return res.status(409).json({ error: 'session_already_exists' });
    }

    try {
      const client = await pool.connect();
      await client.query('BEGIN');

      sessions.set(session_id, {
        client,
        checkpoints: new Map(),
        checkpointCounter: 0,
      });

      res.json({ session_id, status: 'active' });
    } catch (err) {
      res.status(500).json({ error: 'database_error', message: err.message });
    }
  });

  // Create checkpoint
  router.post('/checkpoint', async (req, res) => {
    const { session_id } = req.body;
    const session = sessions.get(session_id);

    if (!session) {
      return res.status(404).json({ error: 'session_not_found' });
    }

    try {
      session.checkpointCounter++;
      const checkpointId = `sp_${session.checkpointCounter}`;

      await session.client.query(`SAVEPOINT ${checkpointId}`);
      session.checkpoints.set(checkpointId, Date.now());

      res.json({ checkpoint_id: checkpointId, session_id });
    } catch (err) {
      res.status(500).json({ error: 'database_error', message: err.message });
    }
  });

  // Rollback to checkpoint
  router.post('/rollback', async (req, res) => {
    const { session_id, checkpoint_id } = req.body;
    const session = sessions.get(session_id);

    if (!session) {
      return res.status(404).json({ error: 'session_not_found' });
    }

    if (!session.checkpoints.has(checkpoint_id)) {
      return res.status(404).json({ error: 'checkpoint_not_found' });
    }

    try {
      await session.client.query(`ROLLBACK TO SAVEPOINT ${checkpoint_id}`);

      // Remove checkpoints created after this one
      for (const [id, time] of session.checkpoints) {
        if (time > session.checkpoints.get(checkpoint_id)) {
          session.checkpoints.delete(id);
        }
      }

      res.json({ status: 'rolled_back', checkpoint_id });
    } catch (err) {
      res.status(500).json({ error: 'database_error', message: err.message });
    }
  });

  // End session
  router.post('/end', async (req, res) => {
    const { session_id } = req.body;
    const session = sessions.get(session_id);

    if (!session) {
      return res.status(404).json({ error: 'session_not_found' });
    }

    try {
      await session.client.query('ROLLBACK');
      session.client.release();
      sessions.delete(session_id);

      res.json({ status: 'ended', session_id });
    } catch (err) {
      res.status(500).json({ error: 'database_error', message: err.message });
    }
  });

  return router;
}

/**
 * Middleware that injects VenomQA-controlled connections into requests.
 *
 * When a VenomQA session is active (X-VenomQA-Session header present),
 * req.db will be the session's connection. Otherwise, it gets a new
 * connection from the pool.
 *
 * @param {Pool} pool - PostgreSQL pool
 * @returns {Function} Express middleware
 */
function venomqaMiddleware(pool) {
  return async (req, res, next) => {
    const sessionId = req.headers['x-venomqa-session'];

    if (sessionId && sessions.has(sessionId)) {
      // Use VenomQA's controlled connection
      req.db = sessions.get(sessionId).client;
      req.venomqaSession = sessionId;
      // Don't release - VenomQA controls the lifecycle
      req.releaseDb = () => {};
    } else {
      // Normal operation - get connection from pool
      req.db = await pool.connect();
      req.releaseDb = () => req.db.release();
    }

    // Clean up on response finish
    res.on('finish', () => {
      if (!req.venomqaSession) {
        req.releaseDb();
      }
    });

    next();
  };
}

/**
 * Helper to get the database client from a request.
 * Use this in your route handlers.
 *
 * @param {Request} req - Express request
 * @returns {Client} PostgreSQL client
 */
function getDb(req) {
  if (!req.db) {
    throw new Error('Database not available. Did you add venomqaMiddleware?');
  }
  return req.db;
}

module.exports = {
  venomqaRouter,
  venomqaMiddleware,
  getDb,
  sessions, // Exported for testing
};

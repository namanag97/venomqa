# VenomBay: Peer-to-Peer Marketplace Specification

## Overview

VenomBay is a peer-to-peer marketplace where users can list items for sale, make offers, and complete transactions with escrow-based payments. The platform supports auctions, fixed-price listings, and negotiated sales with a comprehensive dispute resolution system.

This specification is designed to expose hard problems in stateful testing:
- Complex multi-entity state machines with interdependencies
- Race conditions in inventory and bidding
- Distributed transaction failures (payment + fulfillment)
- Concurrent user scenarios
- Time-based state transitions
- Administrative interventions mid-flow

---

## 1. Domain Description

### Core Concepts

**VenomBay** connects sellers and buyers:
- **Sellers** list items with various sale types (fixed price, auction, make-offer)
- **Buyers** browse, bid, make offers, or purchase directly
- **Escrow** holds funds during transaction until delivery confirmed
- **Disputes** handle disagreements between parties
- **Reviews** build trust after completed transactions

### Key Features
- Multi-quantity listings (seller has 5 of same item)
- Reserved inventory during checkout (15-minute hold)
- Auction with auto-extend on last-minute bids
- Offer/counter-offer negotiation chains
- Partial refunds and dispute resolution
- Seller vacation mode (pause all listings)
- Buyer watchlists with price drop notifications

---

## 2. Entities and State Machines

### 2.1 User Entity

```
States: UNVERIFIED → ACTIVE ⇄ SUSPENDED → BANNED
                ↓         ↓
           DELETED    VACATION
```

| State | Description |
|-------|-------------|
| `UNVERIFIED` | Email not yet confirmed |
| `ACTIVE` | Normal operational state |
| `SUSPENDED` | Temporarily restricted (policy violation) |
| `BANNED` | Permanently removed |
| `VACATION` | Self-imposed pause (seller only) |
| `DELETED` | Soft-deleted, data retained 30 days |

**State Transition Rules:**
- `UNVERIFIED → ACTIVE`: Email verified
- `ACTIVE → SUSPENDED`: Admin action or automatic (3 disputes lost)
- `SUSPENDED → ACTIVE`: Admin reinstatement or appeal approved
- `SUSPENDED → BANNED`: Repeated violations
- `ACTIVE → VACATION`: Seller self-service (all listings paused)
- `VACATION → ACTIVE`: Seller self-service
- `ACTIVE → DELETED`: User self-service (no open transactions)
- `UNVERIFIED → DELETED`: User self-service

### 2.2 Listing Entity

```
                    ┌──────────────┐
                    │    DRAFT     │
                    └──────┬───────┘
                           │ publish
                           ▼
┌──────────┐       ┌──────────────┐       ┌──────────────┐
│  PAUSED  │◄─────►│    ACTIVE    │──────►│    SOLD      │
└──────────┘       └──────┬───────┘       └──────────────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
       ┌──────────┐ ┌──────────┐ ┌──────────┐
       │ RESERVED │ │ EXPIRED  │ │ CANCELLED│
       └──────────┘ └──────────┘ └──────────┘
              │
              ▼
       ┌──────────┐
       │  ACTIVE  │ (reservation timeout)
       └──────────┘
```

| State | Description |
|-------|-------------|
| `DRAFT` | Created but not visible to buyers |
| `ACTIVE` | Live and purchasable |
| `RESERVED` | Quantity held for in-progress checkout |
| `PAUSED` | Seller-initiated or vacation mode |
| `SOLD` | All quantity purchased |
| `EXPIRED` | Listing duration ended (auctions) |
| `CANCELLED` | Seller cancelled |

**Key Fields:**
```typescript
interface Listing {
  id: string;
  sellerId: string;
  title: string;
  description: string;
  category: string;
  condition: 'NEW' | 'LIKE_NEW' | 'GOOD' | 'FAIR' | 'POOR';

  // Pricing
  saleType: 'FIXED_PRICE' | 'AUCTION' | 'MAKE_OFFER';
  price: number;              // Fixed price or starting bid
  reservePrice?: number;      // Auction minimum
  buyNowPrice?: number;       // Auction instant purchase

  // Inventory
  totalQuantity: number;
  availableQuantity: number;  // totalQuantity - reserved - sold
  reservedQuantity: number;
  soldQuantity: number;

  // Timing
  state: ListingState;
  publishedAt?: Date;
  expiresAt?: Date;           // For auctions

  // Auction specific
  currentBid?: number;
  currentBidderId?: string;
  bidCount: number;
  autoExtendMinutes: number;  // Extend if bid in last N minutes

  // Metadata
  version: number;            // Optimistic locking
  createdAt: Date;
  updatedAt: Date;
}
```

### 2.3 Order Entity

```
                    ┌──────────────────┐
                    │ PENDING_PAYMENT  │
                    └────────┬─────────┘
                             │ payment_received
                             ▼
                    ┌──────────────────┐
         ┌─────────│     PAID         │─────────┐
         │         └────────┬─────────┘         │
         │                  │ ship               │ cancel
         │                  ▼                    ▼
         │         ┌──────────────────┐  ┌──────────────┐
         │         │    SHIPPED       │  │  CANCELLED   │
         │         └────────┬─────────┘  └──────────────┘
         │                  │ deliver            ▲
         │                  ▼                    │
         │         ┌──────────────────┐          │
         │         │   DELIVERED      │──────────┤
         │         └────────┬─────────┘          │
         │                  │                    │
         │    ┌─────────────┼─────────────┐      │
         │    │ confirm     │ dispute     │      │
         │    ▼             ▼             │      │
         │ ┌────────┐ ┌───────────┐       │      │
         │ │COMPLETE│ │ DISPUTED  │───────┼──────┘
         │ └────────┘ └─────┬─────┘       │
         │                  │ resolve     │
         │                  ▼             │
         │            ┌───────────┐       │
         └───────────►│ REFUNDED  │◄──────┘
                      └───────────┘
```

| State | Description |
|-------|-------------|
| `PENDING_PAYMENT` | Order created, awaiting payment |
| `PAID` | Payment received, in escrow |
| `SHIPPED` | Seller marked as shipped |
| `DELIVERED` | Carrier confirmed delivery |
| `COMPLETED` | Buyer confirmed receipt, funds released |
| `DISPUTED` | Buyer opened dispute |
| `REFUNDED` | Full or partial refund issued |
| `CANCELLED` | Order cancelled before completion |

**Key Fields:**
```typescript
interface Order {
  id: string;
  orderNumber: string;        // Human-readable ORDER-XXXXX

  // Parties
  buyerId: string;
  sellerId: string;

  // Items
  listingId: string;
  listingSnapshotId: string;  // Immutable copy at purchase time
  quantity: number;
  unitPrice: number;

  // Financials
  subtotal: number;
  shippingCost: number;
  platformFee: number;        // 10% of subtotal
  totalAmount: number;

  // Escrow
  escrowId: string;
  escrowState: 'HELD' | 'RELEASED' | 'REFUNDED' | 'PARTIAL_REFUND';

  // Shipping
  shippingAddress: Address;
  trackingNumber?: string;
  carrier?: string;
  shippedAt?: Date;
  deliveredAt?: Date;

  // State
  state: OrderState;
  stateHistory: StateTransition[];

  // Timing
  paymentDeadline: Date;      // 24 hours from creation
  shipByDeadline?: Date;      // 5 days from payment
  confirmByDeadline?: Date;   // 3 days from delivery

  version: number;
  createdAt: Date;
  updatedAt: Date;
}
```

### 2.4 Offer Entity (for Make-Offer listings)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   PENDING   │────►│  COUNTERED  │────►│  ACCEPTED   │
└──────┬──────┘     └──────┬──────┘     └─────────────┘
       │                   │
       ▼                   ▼
┌─────────────┐     ┌─────────────┐
│  DECLINED   │     │   EXPIRED   │
└─────────────┘     └─────────────┘
       ▲
       │
┌──────┴──────┐
│ WITHDRAWN   │
└─────────────┘
```

**Key Fields:**
```typescript
interface Offer {
  id: string;
  listingId: string;
  buyerId: string;
  sellerId: string;

  // Offer chain
  parentOfferId?: string;     // For counter-offers
  amount: number;
  quantity: number;
  message?: string;

  // State
  state: OfferState;
  expiresAt: Date;            // 48 hours default

  // If accepted
  resultingOrderId?: string;

  createdAt: Date;
  updatedAt: Date;
}
```

### 2.5 Bid Entity (for Auctions)

```
┌─────────────┐     ┌─────────────┐
│   ACTIVE    │────►│   OUTBID    │
└──────┬──────┘     └─────────────┘
       │
       ├────────────────┐
       ▼                ▼
┌─────────────┐  ┌─────────────┐
│   WINNING   │  │  RETRACTED  │
└──────┬──────┘  └─────────────┘
       │
       ▼
┌─────────────┐
│     WON     │
└─────────────┘
```

**Key Fields:**
```typescript
interface Bid {
  id: string;
  listingId: string;
  bidderId: string;

  amount: number;
  maxAutoBid?: number;        // Proxy bidding

  state: BidState;
  outbidAt?: Date;

  createdAt: Date;
}
```

### 2.6 Dispute Entity

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│    OPEN     │────►│ UNDER_REVIEW│────►│  RESOLVED   │
└──────┬──────┘     └─────────────┘     └─────────────┘
       │                                       ▲
       ▼                                       │
┌─────────────┐                                │
│  ESCALATED  │────────────────────────────────┘
└─────────────┘
```

**Key Fields:**
```typescript
interface Dispute {
  id: string;
  orderId: string;
  openedBy: 'BUYER' | 'SELLER';

  reason: DisputeReason;
  description: string;
  evidence: Evidence[];

  state: DisputeState;

  // Resolution
  resolution?: 'FAVOR_BUYER' | 'FAVOR_SELLER' | 'SPLIT';
  refundAmount?: number;
  adminNotes?: string;

  // Communication
  messages: DisputeMessage[];

  createdAt: Date;
  resolvedAt?: Date;
}

type DisputeReason =
  | 'ITEM_NOT_RECEIVED'
  | 'ITEM_NOT_AS_DESCRIBED'
  | 'DAMAGED_IN_SHIPPING'
  | 'WRONG_ITEM'
  | 'COUNTERFEIT';
```

### 2.7 Escrow Entity

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   PENDING   │────►│    HELD     │────►│  RELEASED   │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  REFUNDED   │
                    └─────────────┘
```

**Key Fields:**
```typescript
interface Escrow {
  id: string;
  orderId: string;

  amount: number;
  currency: string;

  state: EscrowState;

  // Payment details
  paymentIntentId: string;    // Stripe reference
  capturedAt?: Date;
  releasedAt?: Date;
  refundedAt?: Date;

  // Partial refund tracking
  refundedAmount: number;
  releasedAmount: number;

  createdAt: Date;
  updatedAt: Date;
}
```

### 2.8 Cart/Reservation Entity

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   ACTIVE    │────►│  CHECKING   │────►│ CONVERTED   │
└──────┬──────┘     │    _OUT     │     └─────────────┘
       │            └──────┬──────┘
       │                   │
       ▼                   ▼
┌─────────────┐     ┌─────────────┐
│  ABANDONED  │     │   EXPIRED   │
└─────────────┘     └─────────────┘
```

**Key Fields:**
```typescript
interface Cart {
  id: string;
  userId: string;

  items: CartItem[];

  state: CartState;

  // Reservation (when checking out)
  reservationId?: string;
  reservationExpiresAt?: Date;  // 15 minutes

  createdAt: Date;
  updatedAt: Date;
}

interface CartItem {
  listingId: string;
  quantity: number;
  priceAtAdd: number;
  addedAt: Date;
}

interface Reservation {
  id: string;
  cartId: string;

  items: ReservationItem[];

  state: 'ACTIVE' | 'CONVERTED' | 'EXPIRED' | 'RELEASED';
  expiresAt: Date;

  createdAt: Date;
}

interface ReservationItem {
  listingId: string;
  quantity: number;
  lockedPrice: number;
}
```

---

## 3. API Endpoints

### 3.1 Authentication & Users

#### `POST /api/v1/auth/register`
Create new user account.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "displayName": "John Doe",
  "acceptedTermsVersion": "2024-01"
}
```

**Response:** `201 Created`
```json
{
  "userId": "usr_abc123",
  "email": "user@example.com",
  "state": "UNVERIFIED",
  "verificationEmailSent": true
}
```

#### `POST /api/v1/auth/verify-email`
Verify email address.

**Request:**
```json
{
  "token": "verification_token_xyz"
}
```

**Response:** `200 OK`
```json
{
  "userId": "usr_abc123",
  "state": "ACTIVE"
}
```

#### `POST /api/v1/auth/login`
Authenticate user.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

**Response:** `200 OK`
```json
{
  "accessToken": "eyJhbG...",
  "refreshToken": "refresh_xyz",
  "expiresIn": 3600,
  "user": {
    "id": "usr_abc123",
    "email": "user@example.com",
    "displayName": "John Doe",
    "state": "ACTIVE"
  }
}
```

#### `GET /api/v1/users/me`
Get current user profile.

**Response:** `200 OK`
```json
{
  "id": "usr_abc123",
  "email": "user@example.com",
  "displayName": "John Doe",
  "state": "ACTIVE",
  "sellerRating": 4.8,
  "sellerReviewCount": 42,
  "buyerRating": 4.9,
  "buyerReviewCount": 15,
  "memberSince": "2023-01-15T00:00:00Z",
  "vacationMode": false
}
```

#### `PUT /api/v1/users/me`
Update user profile.

**Request:**
```json
{
  "displayName": "John D.",
  "bio": "Vintage collector",
  "shippingAddresses": [...]
}
```

#### `POST /api/v1/users/me/vacation`
Enable vacation mode (seller).

**Request:**
```json
{
  "enabled": true,
  "returnDate": "2024-02-15",
  "autoReplyMessage": "On vacation until Feb 15"
}
```

**Response:** `200 OK`
```json
{
  "vacationMode": true,
  "listingsPaused": 12,
  "activeOffersDeclined": 3
}
```

---

### 3.2 Listings

#### `POST /api/v1/listings`
Create new listing (draft).

**Request:**
```json
{
  "title": "Vintage Camera - Canon AE-1",
  "description": "Excellent condition, fully functional...",
  "category": "electronics.cameras.film",
  "condition": "GOOD",
  "saleType": "FIXED_PRICE",
  "price": 299.99,
  "quantity": 1,
  "shippingOptions": [
    {
      "method": "STANDARD",
      "price": 12.99,
      "estimatedDays": "5-7"
    },
    {
      "method": "EXPRESS",
      "price": 24.99,
      "estimatedDays": "2-3"
    }
  ],
  "images": ["img_abc", "img_def"]
}
```

**Response:** `201 Created`
```json
{
  "id": "lst_xyz789",
  "state": "DRAFT",
  "...all fields..."
}
```

#### `POST /api/v1/listings` (Auction variant)
```json
{
  "title": "Rare Baseball Card - 1952 Topps Mickey Mantle",
  "saleType": "AUCTION",
  "price": 100.00,
  "reservePrice": 500.00,
  "buyNowPrice": 2000.00,
  "duration": "7_DAYS",
  "autoExtendMinutes": 5,
  "...other fields..."
}
```

#### `POST /api/v1/listings/{listingId}/publish`
Publish draft listing.

**Response:** `200 OK`
```json
{
  "id": "lst_xyz789",
  "state": "ACTIVE",
  "publishedAt": "2024-01-15T10:30:00Z",
  "expiresAt": "2024-01-22T10:30:00Z"
}
```

#### `GET /api/v1/listings/{listingId}`
Get listing details.

**Response:** `200 OK`
```json
{
  "id": "lst_xyz789",
  "sellerId": "usr_abc123",
  "title": "Vintage Camera - Canon AE-1",
  "state": "ACTIVE",
  "saleType": "FIXED_PRICE",
  "price": 299.99,
  "availableQuantity": 1,
  "reservedQuantity": 0,
  "version": 3,
  "...all fields..."
}
```

#### `PUT /api/v1/listings/{listingId}`
Update listing.

**Request:**
```json
{
  "price": 279.99,
  "expectedVersion": 3
}
```

**Response:** `200 OK` or `409 Conflict` (version mismatch)

#### `POST /api/v1/listings/{listingId}/pause`
Pause listing.

#### `POST /api/v1/listings/{listingId}/resume`
Resume paused listing.

#### `DELETE /api/v1/listings/{listingId}`
Cancel listing (if no pending orders).

#### `GET /api/v1/listings`
Search/browse listings.

**Query Parameters:**
- `q` - Search query
- `category` - Category filter
- `saleType` - FIXED_PRICE, AUCTION, MAKE_OFFER
- `minPrice`, `maxPrice` - Price range
- `condition` - Condition filter
- `sort` - relevance, price_asc, price_desc, ending_soon, newest
- `page`, `limit` - Pagination

**Response:** `200 OK`
```json
{
  "items": [...],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 1543,
    "hasMore": true
  }
}
```

---

### 3.3 Cart & Checkout

#### `GET /api/v1/cart`
Get user's cart.

**Response:** `200 OK`
```json
{
  "id": "cart_123",
  "items": [
    {
      "listingId": "lst_xyz789",
      "quantity": 1,
      "priceAtAdd": 299.99,
      "currentPrice": 279.99,
      "available": true,
      "availableQuantity": 1
    }
  ],
  "subtotal": 279.99,
  "itemCount": 1,
  "hasUnavailableItems": false,
  "hasPriceChanges": true
}
```

#### `POST /api/v1/cart/items`
Add item to cart.

**Request:**
```json
{
  "listingId": "lst_xyz789",
  "quantity": 1
}
```

**Response:** `200 OK` or `409 Conflict` (insufficient quantity)

#### `PUT /api/v1/cart/items/{listingId}`
Update cart item quantity.

**Request:**
```json
{
  "quantity": 2
}
```

#### `DELETE /api/v1/cart/items/{listingId}`
Remove item from cart.

#### `POST /api/v1/cart/reserve`
**CRITICAL ENDPOINT** - Reserve inventory for checkout.

**Request:**
```json
{
  "shippingAddressId": "addr_456"
}
```

**Response:** `200 OK`
```json
{
  "reservationId": "res_789",
  "expiresAt": "2024-01-15T10:45:00Z",
  "items": [
    {
      "listingId": "lst_xyz789",
      "quantity": 1,
      "lockedPrice": 279.99,
      "reserved": true
    }
  ],
  "totals": {
    "subtotal": 279.99,
    "shipping": 12.99,
    "platformFee": 28.00,
    "total": 320.98
  }
}
```

**Error Response:** `409 Conflict`
```json
{
  "error": "INSUFFICIENT_INVENTORY",
  "details": {
    "listingId": "lst_xyz789",
    "requested": 2,
    "available": 1
  }
}
```

#### `POST /api/v1/checkout`
**CRITICAL ENDPOINT** - Complete purchase.

**Request:**
```json
{
  "reservationId": "res_789",
  "paymentMethodId": "pm_stripe_abc",
  "expectedTotal": 320.98
}
```

**Response:** `201 Created`
```json
{
  "orderId": "ord_abc123",
  "orderNumber": "ORDER-20240115-ABC1",
  "state": "PENDING_PAYMENT",
  "paymentIntentId": "pi_stripe_xyz",
  "paymentIntentClientSecret": "pi_xyz_secret_abc"
}
```

**Error Responses:**
- `409 Conflict` - Reservation expired
- `409 Conflict` - Price changed (expectedTotal mismatch)
- `402 Payment Required` - Payment failed

#### `POST /api/v1/checkout/confirm`
Confirm payment completion (webhook or client confirmation).

**Request:**
```json
{
  "orderId": "ord_abc123",
  "paymentIntentId": "pi_stripe_xyz"
}
```

**Response:** `200 OK`
```json
{
  "orderId": "ord_abc123",
  "state": "PAID",
  "escrowId": "esc_xyz",
  "escrowState": "HELD"
}
```

---

### 3.4 Orders

#### `GET /api/v1/orders`
List user's orders (as buyer or seller).

**Query Parameters:**
- `role` - buyer, seller, all
- `state` - Filter by state
- `page`, `limit`

#### `GET /api/v1/orders/{orderId}`
Get order details.

**Response:** `200 OK`
```json
{
  "id": "ord_abc123",
  "orderNumber": "ORDER-20240115-ABC1",
  "state": "PAID",
  "buyer": {
    "id": "usr_buyer",
    "displayName": "Buyer Bob"
  },
  "seller": {
    "id": "usr_seller",
    "displayName": "Seller Sally"
  },
  "listing": {
    "id": "lst_xyz789",
    "title": "Vintage Camera - Canon AE-1",
    "snapshotId": "snap_123"
  },
  "quantity": 1,
  "unitPrice": 279.99,
  "subtotal": 279.99,
  "shippingCost": 12.99,
  "platformFee": 28.00,
  "totalAmount": 320.98,
  "escrow": {
    "id": "esc_xyz",
    "state": "HELD",
    "amount": 320.98
  },
  "shippingAddress": {...},
  "shipByDeadline": "2024-01-20T10:30:00Z",
  "stateHistory": [
    {"state": "PENDING_PAYMENT", "at": "2024-01-15T10:30:00Z"},
    {"state": "PAID", "at": "2024-01-15T10:32:00Z"}
  ]
}
```

#### `POST /api/v1/orders/{orderId}/ship`
Mark order as shipped (seller).

**Request:**
```json
{
  "carrier": "USPS",
  "trackingNumber": "9400111899223456789012"
}
```

**Response:** `200 OK`
```json
{
  "state": "SHIPPED",
  "shippedAt": "2024-01-16T14:00:00Z",
  "trackingUrl": "https://tools.usps.com/..."
}
```

#### `POST /api/v1/orders/{orderId}/deliver`
Mark order as delivered (carrier webhook or manual).

**Request:**
```json
{
  "source": "CARRIER_WEBHOOK",
  "deliveredAt": "2024-01-19T11:00:00Z"
}
```

#### `POST /api/v1/orders/{orderId}/confirm`
Confirm receipt and release escrow (buyer).

**Response:** `200 OK`
```json
{
  "state": "COMPLETED",
  "escrow": {
    "state": "RELEASED",
    "releasedAt": "2024-01-19T15:00:00Z"
  }
}
```

#### `POST /api/v1/orders/{orderId}/cancel`
Cancel order.

**Request:**
```json
{
  "reason": "BUYER_REQUEST",
  "note": "Changed my mind"
}
```

**Validation:**
- Buyer can cancel: PENDING_PAYMENT, PAID (before shipment)
- Seller can cancel: PAID (before shipment, with penalty)
- Auto-refund triggered for PAID orders

---

### 3.5 Offers (Make-Offer Listings)

#### `POST /api/v1/listings/{listingId}/offers`
Make an offer.

**Request:**
```json
{
  "amount": 250.00,
  "quantity": 1,
  "message": "Would you accept $250? I can pay immediately."
}
```

**Response:** `201 Created`
```json
{
  "id": "off_123",
  "state": "PENDING",
  "amount": 250.00,
  "expiresAt": "2024-01-17T10:30:00Z"
}
```

#### `GET /api/v1/offers`
List user's offers (as buyer or seller).

#### `GET /api/v1/offers/{offerId}`
Get offer details.

#### `POST /api/v1/offers/{offerId}/accept`
Accept offer (seller).

**Response:** `200 OK`
```json
{
  "offer": {
    "id": "off_123",
    "state": "ACCEPTED"
  },
  "reservation": {
    "id": "res_offer_789",
    "expiresAt": "2024-01-15T10:45:00Z"
  },
  "checkoutUrl": "/checkout?reservation=res_offer_789"
}
```

#### `POST /api/v1/offers/{offerId}/decline`
Decline offer (seller).

#### `POST /api/v1/offers/{offerId}/counter`
Counter offer (seller).

**Request:**
```json
{
  "amount": 275.00,
  "message": "I can do $275, that's my best price."
}
```

**Response:** `201 Created`
```json
{
  "id": "off_124",
  "parentOfferId": "off_123",
  "state": "PENDING",
  "amount": 275.00
}
```

#### `POST /api/v1/offers/{offerId}/withdraw`
Withdraw offer (buyer).

---

### 3.6 Bids (Auctions)

#### `POST /api/v1/listings/{listingId}/bids`
Place bid.

**Request:**
```json
{
  "amount": 150.00,
  "maxAutoBid": 200.00
}
```

**Response:** `201 Created`
```json
{
  "id": "bid_123",
  "state": "ACTIVE",
  "amount": 150.00,
  "isHighBidder": true,
  "listing": {
    "currentBid": 150.00,
    "bidCount": 5,
    "expiresAt": "2024-01-22T10:35:00Z"
  }
}
```

**Note:** If listing was within `autoExtendMinutes` of ending, `expiresAt` is extended.

**Error Response:** `409 Conflict`
```json
{
  "error": "BID_TOO_LOW",
  "minimumBid": 155.00,
  "currentBid": 150.00
}
```

#### `GET /api/v1/listings/{listingId}/bids`
Get bid history for listing.

#### `POST /api/v1/listings/{listingId}/buy-now`
Buy now at fixed price (auctions with buyNowPrice).

---

### 3.7 Disputes

#### `POST /api/v1/orders/{orderId}/disputes`
Open dispute (buyer).

**Request:**
```json
{
  "reason": "ITEM_NOT_AS_DESCRIBED",
  "description": "The camera has a crack in the viewfinder that wasn't disclosed.",
  "evidence": [
    {
      "type": "IMAGE",
      "url": "https://...",
      "description": "Photo showing crack"
    }
  ]
}
```

**Response:** `201 Created`
```json
{
  "id": "dsp_123",
  "state": "OPEN",
  "order": {...}
}
```

#### `GET /api/v1/disputes/{disputeId}`
Get dispute details.

#### `POST /api/v1/disputes/{disputeId}/messages`
Add message to dispute.

**Request:**
```json
{
  "message": "I've attached additional photos.",
  "evidence": [...]
}
```

#### `POST /api/v1/disputes/{disputeId}/escalate`
Escalate to platform support.

#### `POST /api/v1/disputes/{disputeId}/resolve` (Admin only)
Resolve dispute.

**Request:**
```json
{
  "resolution": "FAVOR_BUYER",
  "refundAmount": 320.98,
  "adminNotes": "Seller did not disclose damage."
}
```

---

### 3.8 Reviews

#### `POST /api/v1/orders/{orderId}/reviews`
Leave review (after order completed).

**Request:**
```json
{
  "rating": 5,
  "title": "Excellent seller!",
  "body": "Item exactly as described, fast shipping.",
  "aspects": {
    "itemAsDescribed": 5,
    "communication": 5,
    "shippingSpeed": 4
  }
}
```

**Validation:**
- Order must be COMPLETED
- Can only leave one review per order
- Review window: 60 days after completion

#### `GET /api/v1/users/{userId}/reviews`
Get user's reviews.

---

### 3.9 Notifications & Watchlist

#### `GET /api/v1/notifications`
Get user's notifications.

#### `POST /api/v1/watchlist`
Add listing to watchlist.

**Request:**
```json
{
  "listingId": "lst_xyz789",
  "notifyPriceDrop": true,
  "notifyEndingSoon": true
}
```

#### `GET /api/v1/watchlist`
Get user's watchlist.

---

### 3.10 Admin Endpoints

#### `POST /api/v1/admin/users/{userId}/suspend`
Suspend user.

**Request:**
```json
{
  "reason": "POLICY_VIOLATION",
  "note": "Multiple counterfeit item reports",
  "duration": "30_DAYS"
}
```

#### `POST /api/v1/admin/users/{userId}/reinstate`
Reinstate suspended user.

#### `POST /api/v1/admin/users/{userId}/ban`
Permanently ban user.

#### `POST /api/v1/admin/listings/{listingId}/remove`
Remove listing (policy violation).

#### `GET /api/v1/admin/disputes`
List disputes for review.

---

## 4. State Transitions by API

| Endpoint | Entity | From State(s) | To State |
|----------|--------|---------------|----------|
| `POST /auth/verify-email` | User | UNVERIFIED | ACTIVE |
| `POST /users/me/vacation` | User | ACTIVE | VACATION |
| `POST /listings/{id}/publish` | Listing | DRAFT | ACTIVE |
| `POST /listings/{id}/pause` | Listing | ACTIVE | PAUSED |
| `POST /cart/reserve` | Listing | ACTIVE | RESERVED* |
| `POST /checkout` | Order | (created) | PENDING_PAYMENT |
| `POST /checkout/confirm` | Order | PENDING_PAYMENT | PAID |
| `POST /orders/{id}/ship` | Order | PAID | SHIPPED |
| `POST /orders/{id}/deliver` | Order | SHIPPED | DELIVERED |
| `POST /orders/{id}/confirm` | Order | DELIVERED | COMPLETED |
| `POST /orders/{id}/cancel` | Order | PENDING_PAYMENT, PAID | CANCELLED |
| `POST /orders/{id}/disputes` | Order | DELIVERED | DISPUTED |
| `POST /offers/{id}/accept` | Offer | PENDING | ACCEPTED |
| `POST /offers/{id}/decline` | Offer | PENDING | DECLINED |
| `POST /offers/{id}/counter` | Offer | PENDING | COUNTERED |
| `POST /listings/{id}/bids` | Bid | (created) | ACTIVE |
| `POST /disputes/{id}/resolve` | Dispute | OPEN, UNDER_REVIEW | RESOLVED |

*Listing stays ACTIVE but `reservedQuantity` increases, `availableQuantity` decreases.

---

## 5. Invariants (Business Rules)

### 5.1 Inventory Invariants

**INV-001: Quantity Conservation**
```
listing.totalQuantity = listing.availableQuantity + listing.reservedQuantity + listing.soldQuantity
```
Must hold at ALL times, across ALL operations.

**INV-002: No Overselling**
```
∀ listing: listing.soldQuantity ≤ listing.totalQuantity
```

**INV-003: Reservation Consistency**
```
listing.reservedQuantity = SUM(active_reservations.quantity WHERE listingId = listing.id)
```

**INV-004: No Negative Quantities**
```
listing.availableQuantity ≥ 0
listing.reservedQuantity ≥ 0
listing.soldQuantity ≥ 0
```

### 5.2 Financial Invariants

**INV-005: Escrow Balance**
```
∀ escrow: escrow.amount = escrow.releasedAmount + escrow.refundedAmount + escrow.heldAmount
```

**INV-006: Order Total Accuracy**
```
order.totalAmount = order.subtotal + order.shippingCost + order.platformFee
order.subtotal = order.unitPrice × order.quantity
order.platformFee = order.subtotal × 0.10
```

**INV-007: No Money Leakage**
```
∀ completed_order:
  escrow.releasedAmount = order.totalAmount - order.platformFee
  platform_revenue += order.platformFee
```

**INV-008: Refund Bounds**
```
∀ refund: refund.amount ≤ order.totalAmount
```

### 5.3 State Machine Invariants

**INV-009: Valid State Transitions**
All state transitions must follow defined state machine. No skipping states.

**INV-010: Order-Escrow State Consistency**
```
order.state = PAID → escrow.state = HELD
order.state = COMPLETED → escrow.state = RELEASED
order.state = REFUNDED → escrow.state = REFUNDED
```

**INV-011: Listing-Order Consistency**
```
order.state = COMPLETED → listing.soldQuantity increased by order.quantity
```

**INV-012: No Actions on Terminal States**
```
order.state ∈ {COMPLETED, REFUNDED, CANCELLED} → no further state transitions
```

### 5.4 Auction Invariants

**INV-013: Bid Ordering**
```
∀ bid: bid.amount > previous_bid.amount
∀ bid: bid.amount ≥ listing.price (starting bid)
```

**INV-014: Reserve Price**
```
auction.ends ∧ currentBid < reservePrice → listing.state = EXPIRED (not SOLD)
```

**INV-015: Single Winner**
```
∀ auction: COUNT(bids WHERE state = WON) ≤ 1
```

**INV-016: Auto-Extend Consistency**
```
bid.createdAt > (listing.expiresAt - autoExtendMinutes) →
  listing.expiresAt = bid.createdAt + autoExtendMinutes
```

### 5.5 User Invariants

**INV-017: Vacation Mode Effects**
```
user.state = VACATION → ∀ user.listings: state ∈ {PAUSED, DRAFT, SOLD, CANCELLED}
```

**INV-018: Suspended User Restrictions**
```
user.state = SUSPENDED →
  cannot create listings
  cannot make purchases
  cannot make offers/bids
  existing orders continue to completion
```

**INV-019: Deletion Prerequisites**
```
user.requestDelete →
  COUNT(open_orders) = 0
  COUNT(open_disputes) = 0
```

### 5.6 Offer Invariants

**INV-020: Offer Chain Integrity**
```
∀ counter_offer: parentOffer.state = COUNTERED
∀ accepted_offer: no other offers on same listing accepted
```

**INV-021: Offer Exclusivity**
```
offer.state = ACCEPTED → listing.availableQuantity reduced by offer.quantity
```

### 5.7 Timing Invariants

**INV-022: Deadline Enforcement**
```
order.state = PENDING_PAYMENT ∧ now > paymentDeadline →
  order.state = CANCELLED (automatic)
```

**INV-023: Ship By Deadline**
```
order.state = PAID ∧ now > shipByDeadline →
  buyer.canCancel = true
  seller.penaltyApplied = true
```

**INV-024: Auto-Confirm**
```
order.state = DELIVERED ∧ now > confirmByDeadline + 3days →
  order.state = COMPLETED (automatic)
```

---

## 6. Tricky Scenarios (Edge Cases)

### 6.1 Race Conditions

#### RACE-001: Simultaneous Last-Item Purchase
**Scenario:** Two buyers try to purchase the last item simultaneously.

**Setup:**
- Listing with `availableQuantity: 1`
- Buyer A and Buyer B both have item in cart
- Both click "checkout" at the same time

**Expected Behavior:**
- Exactly one succeeds with reservation
- Other gets `409 INSUFFICIENT_INVENTORY`
- No overselling (INV-002 holds)

**Testing Approach:**
```
PARALLEL:
  - buyer_a.reserve(listingId, quantity=1)
  - buyer_b.reserve(listingId, quantity=1)
THEN:
  ASSERT exactly_one_succeeded
  ASSERT listing.reservedQuantity = 1
  ASSERT listing.availableQuantity = 0
```

#### RACE-002: Auction Sniping
**Scenario:** Multiple bids in final seconds of auction.

**Setup:**
- Auction ending in 10 seconds
- `autoExtendMinutes: 5`
- Three bidders submit bids rapidly

**Expected Behavior:**
- Each valid bid extends auction by 5 minutes
- Bid ordering maintained (INV-013)
- Single winner determined (INV-015)

#### RACE-003: Offer Accept During Checkout
**Scenario:** Seller accepts offer while buyer is mid-checkout on same listing.

**Setup:**
- Listing with `quantity: 1`
- Buyer A has active reservation
- Offer from Buyer B is pending
- Seller accepts Buyer B's offer

**Expected Behavior:**
- Buyer A's checkout fails (inventory no longer available)
- Buyer B gets reservation
- Only one order created

### 6.2 Distributed Transaction Failures

#### DT-001: Payment Succeeds, Confirmation Fails
**Scenario:** Stripe charges card, but our `/checkout/confirm` endpoint crashes.

**Setup:**
- Order in PENDING_PAYMENT
- Stripe payment_intent succeeds
- Network failure before our DB update

**Expected Behavior:**
- Webhook retry eventually confirms payment
- Order transitions to PAID
- No duplicate charges
- Idempotency key prevents duplicate processing

**Recovery:**
- Stripe webhook: `payment_intent.succeeded`
- System reconciliation job (every 5 min)
- Manual admin intervention endpoint

#### DT-002: Escrow Release Fails
**Scenario:** Buyer confirms receipt, but payment release to seller fails.

**Setup:**
- Order in DELIVERED
- Buyer clicks "confirm"
- Stripe transfer to seller fails

**Expected Behavior:**
- Order stays in intermediate state (COMPLETED but escrow HELD)
- Alert sent to operations
- Retry mechanism with exponential backoff
- Eventually consistent

#### DT-003: Partial Failure in Multi-Item Checkout
**Scenario:** Cart has 3 items from 3 sellers. Reservation succeeds for 2, fails for 1.

**Expected Behavior:**
- Entire reservation fails (atomic)
- No partial reservations
- Clear error message indicating which item failed

### 6.3 State Desynchronization

#### STATE-001: Admin Suspends User Mid-Transaction
**Scenario:** User has order in PAID state, admin suspends user.

**Expected Behavior:**
- Existing order continues normally (INV-018)
- User cannot create new orders
- Seller can still ship
- Buyer can still confirm/dispute

#### STATE-002: Seller Deletes Listing During Checkout
**Scenario:** Buyer has reservation, seller cancels listing.

**Expected Behavior:**
- Reservation remains valid until expiry
- If checkout completes, order proceeds (listing snapshot exists)
- Seller cannot cancel listing with active reservations (validation)

#### STATE-003: Price Change During Checkout
**Scenario:** Seller changes price while buyer has reservation.

**Expected Behavior:**
- Reservation locks price at reservation time
- Checkout succeeds at locked price
- `expectedTotal` check catches any discrepancy

### 6.4 Timing Edge Cases

#### TIME-001: Reservation Expires Mid-Payment
**Scenario:** User starts payment, 15-minute reservation expires, payment completes.

**Expected Behavior:**
- If inventory still available: create order, re-reserve
- If inventory gone: refund payment, show error
- Idempotent: multiple confirm attempts don't create multiple orders

#### TIME-002: Auction Ends With Pending Bid
**Scenario:** Bid submitted at T-1 second, processed after auction end.

**Expected Behavior:**
- Bid timestamped at receipt time
- If timestamp < expiresAt: bid valid, auction extended
- If timestamp >= expiresAt: bid rejected

#### TIME-003: Offer Expires During Counter
**Scenario:** Seller types counter-offer, original offer expires before submit.

**Expected Behavior:**
- Counter-offer fails with "offer expired"
- No orphaned counter-offers

### 6.5 Concurrency Edge Cases

#### CONC-001: Simultaneous Offer Accept and Withdraw
**Scenario:** Buyer withdraws offer exactly as seller accepts.

**Expected Behavior:**
- Exactly one operation succeeds
- If accept wins: order created
- If withdraw wins: no order
- Optimistic locking on offer entity

#### CONC-002: Multiple Tabs Checkout
**Scenario:** Same user opens checkout in two tabs, completes both.

**Expected Behavior:**
- First completion succeeds
- Second fails (reservation already converted)
- No double-charge
- Clear error message

#### CONC-003: Admin and User Simultaneous Action
**Scenario:** Admin removes listing while seller is editing it.

**Expected Behavior:**
- Admin action takes precedence
- Seller edit fails with "listing no longer exists"
- Audit log captures both attempts

### 6.6 Idempotency Requirements

#### IDEMP-001: Checkout Retry
**Scenario:** Network timeout on `/checkout`, client retries.

**Requirements:**
- Same `reservationId` produces same order
- No duplicate orders
- No duplicate payment intents

#### IDEMP-002: Webhook Retry
**Scenario:** Stripe webhook delivered multiple times.

**Requirements:**
- Same `paymentIntentId` processed once
- Order state transitions idempotent
- No duplicate escrow records

#### IDEMP-003: Ship Confirmation Retry
**Scenario:** Seller clicks "Mark Shipped" twice quickly.

**Requirements:**
- Second click no-ops
- `shippedAt` timestamp from first click preserved
- Single tracking notification sent

### 6.7 Data Consistency Edge Cases

#### DATA-001: Listing Snapshot Integrity
**Scenario:** Order references listing that was deleted.

**Requirements:**
- `listingSnapshotId` points to immutable copy
- All order display uses snapshot, not live listing
- Snapshot retained even if listing deleted

#### DATA-002: User Deletion With History
**Scenario:** User requests deletion with past orders.

**Requirements:**
- Orders retained with anonymized user reference
- Reviews retained with anonymized author
- Personal data purged per GDPR

#### DATA-003: Currency Precision
**Scenario:** Calculations result in $10.005 (half-cent).

**Requirements:**
- All money stored as cents (integer)
- Rounding rules defined and consistent
- Platform fee rounding favors platform (round up)

---

## 7. Inter-Journey Dependencies

### 7.1 Journey Map

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           USER JOURNEYS                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌──────────────┐                                                        │
│  │   REGISTER   │──────────────────────────┐                             │
│  └──────┬───────┘                          │                             │
│         │                                  │                             │
│         ▼                                  ▼                             │
│  ┌──────────────┐                  ┌──────────────┐                      │
│  │  LIST ITEM   │                  │    BROWSE    │                      │
│  └──────┬───────┘                  └──────┬───────┘                      │
│         │                                  │                             │
│         │    ┌─────────────────────────────┤                             │
│         │    │                             │                             │
│         │    ▼                             ▼                             │
│         │  ┌──────────────┐        ┌──────────────┐                      │
│         │  │  MAKE OFFER  │        │   ADD CART   │                      │
│         │  └──────┬───────┘        └──────┬───────┘                      │
│         │         │                       │                              │
│         ▼         ▼                       ▼                              │
│  ┌──────────────────────────────────────────────────┐                    │
│  │                  CHECKOUT                         │                    │
│  └──────────────────────┬───────────────────────────┘                    │
│                         │                                                 │
│                         ▼                                                 │
│  ┌──────────────────────────────────────────────────┐                    │
│  │                ORDER FULFILLMENT                  │                    │
│  │  (ship → deliver → confirm)                       │                    │
│  └──────────────────────┬───────────────────────────┘                    │
│                         │                                                 │
│         ┌───────────────┼───────────────┐                                │
│         │               │               │                                │
│         ▼               ▼               ▼                                │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                        │
│  │   REVIEW    │ │   DISPUTE   │ │   REFUND    │                        │
│  └─────────────┘ └──────┬──────┘ └─────────────┘                        │
│                         │                                                │
│                         ▼                                                │
│                  ┌─────────────┐                                         │
│                  │  ESCALATE   │                                         │
│                  └─────────────┘                                         │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Journey Dependencies Matrix

| Journey | Depends On | Blocks | Shared State |
|---------|------------|--------|--------------|
| Register | - | All others | User entity |
| List Item | Register (as seller) | Browse, Offer, Checkout | Listing entity |
| Browse | List Item (items exist) | Add Cart, Make Offer | - |
| Add Cart | Browse | Checkout | Cart, Listing.availableQty |
| Make Offer | Browse, List Item | Checkout (if accepted) | Offer, Listing.availableQty |
| Place Bid | List Item (auction) | Checkout (if won) | Bid, Listing.currentBid |
| Checkout | Cart OR Accepted Offer OR Won Bid | Fulfillment | Order, Escrow, Listing.soldQty |
| Fulfillment | Checkout | Review, Dispute | Order state |
| Review | Fulfillment (completed) | - | Review, User ratings |
| Dispute | Fulfillment (delivered) | Review (blocked until resolved) | Dispute, Order state |
| Refund | Dispute OR Cancel | - | Escrow, Order state |

### 7.3 Cross-Journey Interactions

#### Interaction 1: Seller Journey Affects Buyer Journey

```
SELLER                              BUYER
  │                                   │
  │ create_listing()                  │
  │────────────────►                  │
  │                    listing exists │
  │                                   │ browse()
  │                                   │────────────►
  │                                   │ add_to_cart()
  │                                   │────────────►
  │ update_price()                    │
  │────────────────►                  │
  │                    price changed  │
  │                                   │ checkout()  ← sees new price!
  │                                   │────────────►
```

**Test Scenario:**
1. Seller creates listing at $100
2. Buyer adds to cart (priceAtAdd: $100)
3. Seller updates price to $80
4. Buyer views cart → should see price change warning
5. Buyer proceeds to checkout → locked at $80

#### Interaction 2: Competing Buyers

```
BUYER_A                             BUYER_B
  │                                   │
  │ add_to_cart(qty=1)               │
  │────────────────►                  │ add_to_cart(qty=1)
  │                                   │────────────────►
  │                    both have item in cart          │
  │                    listing.availableQty = 1        │
  │                                   │
  │ reserve()                         │ reserve()
  │────────────────►                  │────────────────►
  │                    RACE CONDITION!                 │
  │ success           │               │ failure        │
  │◄──────────────────                │◄──────────────  │
```

**Test Scenario:**
1. Listing with quantity=1
2. Buyer A and B both add to cart
3. Simultaneous reserve() calls
4. Assert exactly one succeeds
5. Assert inventory invariants hold

#### Interaction 3: Offer Negotiation Affects Direct Purchase

```
BUYER_A (offer)                     BUYER_B (direct)
  │                                   │
  │ make_offer($80)                   │
  │────────────────►                  │
  │                    offer pending  │
  │                                   │
  │                    SELLER         │
  │                      │            │
  │                      │ accept()   │
  │                      │───────────►│
  │                                   │ checkout() ← FAILS!
  │◄──────reservation────             │ inventory reserved
  │                                   │ for offer
```

**Test Scenario:**
1. Listing with quantity=1, accepts offers
2. Buyer A makes offer
3. Buyer B adds to cart
4. Seller accepts Buyer A's offer
5. Buyer B checkout fails

#### Interaction 4: Auction Affects Watchlist Notifications

```
AUCTION                              WATCHERS
  │                                   │
  │ bid placed                        │
  │────────────────►                  │ notification: "new high bid"
  │                                   │────────────────►
  │ auto-extend (last minute bid)    │
  │────────────────►                  │ notification: "auction extended"
  │                                   │────────────────►
  │ auction ends                      │
  │────────────────►                  │ notification: "auction ended"
  │                                   │────────────────►
```

#### Interaction 5: Dispute Affects Review Eligibility

```
BUYER                               SELLER
  │                                   │
  │ order delivered                   │
  │────────────────►                  │
  │                                   │
  │ open_dispute()                    │
  │────────────────►                  │
  │                    dispute open   │
  │                                   │
  │ leave_review() ← BLOCKED!        │
  │────────────────►                  │
  │ "Cannot review during dispute"   │
  │                                   │
  │                    dispute resolved
  │                                   │
  │ leave_review() ← NOW ALLOWED     │
  │────────────────►                  │
```

### 7.4 State Pollution Scenarios

#### Pollution 1: Failed Checkout Leaves Orphaned Reservation

```
Journey A: Add Cart → Reserve → Payment Fails
Journey B: (different user) Browse → Add Cart → Reserve

Issue: Journey A's reservation not properly released
Result: Journey B fails incorrectly
```

**Required Cleanup:**
- Reservation expiry job (every minute)
- Failed payment triggers immediate release
- Checkout failure handler releases reservation

#### Pollution 2: Partial User Deletion

```
Journey A: User requests deletion
Journey B: (admin) Reviewing user's open dispute

Issue: Deletion proceeds while dispute open
Result: Orphaned dispute, data inconsistency
```

**Required Validation:**
- Deletion blocked while open disputes/orders
- Clear error message listing blockers

#### Pollution 3: Stale Cart Data

```
Journey A (Day 1): Add item to cart
Journey B (Day 7): Item sold out
Journey A (Day 8): User returns, clicks checkout

Issue: Cart shows item that's no longer available
```

**Required Handling:**
- Cart fetch validates all items
- Unavailable items marked but kept (user can remove)
- Checkout blocked until cart clean

### 7.5 Critical Path Dependencies

```
CRITICAL PATH: Registration → Listing → Checkout → Fulfillment

Each step MUST complete before next can begin.
Testing approach: Journey dependencies form a DAG.

Level 0 (no deps):     Register
Level 1 (needs user):  List Item, Browse
Level 2 (needs items): Add Cart, Make Offer, Place Bid
Level 3 (needs cart):  Checkout
Level 4 (needs order): Ship, Deliver, Confirm
Level 5 (needs done):  Review, Dispute
```

### 7.6 Recommended Test Execution Order

```
1. SETUP PHASE
   - Register users (buyer, seller, admin)
   - Verify emails
   - Setup payment methods

2. INVENTORY PHASE
   - Seller creates listings (all types)
   - Verify listing states

3. DISCOVERY PHASE
   - Buyer browses, searches
   - Add items to cart
   - Make offers on make-offer listings
   - Place bids on auctions

4. TRANSACTION PHASE
   - Accept/counter offers
   - Complete checkouts
   - Verify inventory decrements

5. FULFILLMENT PHASE
   - Ship orders
   - Confirm deliveries
   - Complete orders

6. POST-TRANSACTION PHASE
   - Leave reviews
   - Open disputes
   - Process refunds

7. EDGE CASE PHASE
   - Race conditions
   - Failure scenarios
   - Admin interventions

8. CLEANUP PHASE
   - Cancel pending orders
   - Delete test listings
   - Soft-delete test users
```

---

## 8. Testing Challenges Summary

### Why Naive Linear Testing Fails

1. **State Pollution**: Tests leave behind reservations, pending orders, offers
2. **Timing Dependencies**: Auctions end, reservations expire, offers expire
3. **Inventory Races**: Multiple parallel tests compete for same inventory
4. **Order Dependencies**: Can't test dispute without completed order
5. **Non-Determinism**: Payment webhooks arrive at unpredictable times

### What a Good Framework Must Handle

1. **Test Isolation**: Each test gets clean state or properly isolated data
2. **Parallel Safety**: Tests can run concurrently without interference
3. **State Machine Validation**: Every transition verified against rules
4. **Invariant Checking**: Business rules verified after every operation
5. **Failure Injection**: Simulate payment failures, network issues
6. **Time Control**: Fast-forward auctions, expire reservations
7. **Concurrent Scenarios**: Model and verify race conditions
8. **Dependency Management**: Execute tests in valid order
9. **Cleanup Hooks**: Release reservations, cancel orders on test failure
10. **Idempotency Verification**: Retry operations, verify no side effects

---

## Appendix A: Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INSUFFICIENT_INVENTORY` | 409 | Not enough quantity available |
| `RESERVATION_EXPIRED` | 409 | Checkout reservation timed out |
| `PRICE_CHANGED` | 409 | Price different from expected |
| `LISTING_UNAVAILABLE` | 409 | Listing paused, sold, or cancelled |
| `BID_TOO_LOW` | 409 | Bid below minimum |
| `AUCTION_ENDED` | 409 | Auction already closed |
| `OFFER_EXPIRED` | 409 | Offer no longer valid |
| `INVALID_STATE_TRANSITION` | 409 | Operation not allowed in current state |
| `VERSION_CONFLICT` | 409 | Optimistic lock failed |
| `USER_SUSPENDED` | 403 | User account suspended |
| `PAYMENT_FAILED` | 402 | Payment processing failed |
| `DUPLICATE_REQUEST` | 409 | Idempotency key already used |

## Appendix B: Webhooks (Inbound)

| Source | Event | Handler |
|--------|-------|---------|
| Stripe | `payment_intent.succeeded` | Confirm order payment |
| Stripe | `payment_intent.failed` | Cancel order, release reservation |
| Stripe | `transfer.failed` | Alert ops, retry escrow release |
| Carrier | `tracking.delivered` | Update order to DELIVERED |

## Appendix C: Background Jobs

| Job | Frequency | Purpose |
|-----|-----------|---------|
| `expire_reservations` | Every 1 min | Release expired checkout reservations |
| `expire_auctions` | Every 1 min | End auctions, create orders for winners |
| `expire_offers` | Every 5 min | Mark expired offers |
| `auto_confirm_orders` | Every 1 hour | Confirm delivered orders past deadline |
| `cancel_unpaid_orders` | Every 5 min | Cancel orders past payment deadline |
| `send_ship_reminders` | Every 1 hour | Remind sellers to ship |
| `reconcile_payments` | Every 5 min | Sync Stripe state with orders |

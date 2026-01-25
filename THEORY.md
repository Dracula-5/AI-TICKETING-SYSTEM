# AI Ticketing System - Technical Theory & Architecture

## System Overview

The AI Ticketing System is a modern, full-stack web application designed for managing support tickets in organizations with multi-tenant support. It leverages artificial intelligence for intelligent ticket routing and includes comprehensive SLA monitoring capabilities.

---

## System Architecture

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         USER MACHINE / BROWSER                              │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │
                ┌─────────────┴─────────────┐
                ▼                           ▼
    ┌───────────────────────┐   ┌──────────────────────┐
    │  FRONTEND (Port 3000) │   │  Browser DevTools    │
    │  ─────────────────    │   │  (F12 for debugging) │
    │  • React App          │   └──────────────────────┘
    │  • Material-UI        │
    │  • Dark Mode Toggle   │
    │  • Responsive Design  │
    │  • 11 Pages           │
    │  • Modern Styling     │
    └──────────┬────────────┘
               │
    ┌──────────▼──────────────────────────────────────────────┐
    │        HTTP/JSON Requests (Axios)                       │
    │        CORS: localhost:3000 ↔ localhost:8000           │
    └──────────┬──────────────────────────────────────────────┘
               │
               ▼
    ┌──────────────────────────────────────────────────────────┐
    │      BACKEND API SERVER (Port 8000)                      │
    │      ──────────────────────────────────────             │
    │                                                           │
    │  FastAPI + Uvicorn (Auto-reload enabled)               │
    │                                                           │
    │  ┌────────────────────────────────────────────────────┐ │
    │  │  API Endpoints (/routers)                          │ │
    │  │  ────────────────────────────────────              │ │
    │  │  • POST   /auth/login              (user login)   │ │
    │  │  • GET    /auth/me                 (current user)  │ │
    │  │  • POST   /tickets                 (create)       │ │
    │  │  • GET    /tickets                 (list)         │ │
    │  │  • GET    /tickets/{id}            (detail)       │ │
    │  │  • PUT    /tickets/{id}            (update)       │ │
    │  │  • POST   /comments                (add comment)  │ │
    │  │  • GET    /users                   (list users)   │ │
    │  │  And more endpoints...                            │ │
    │  └────────────────────────────────────────────────────┘ │
    │                                                           │
    │  ┌────────────────────────────────────────────────────┐ │
    │  │  Core Services                                     │ │
    │  │  ────────────────                                  │ │
    │  │  • auth_utils.py      (JWT token management)      │ │
    │  │  • security.py        (password hashing)          │ │
    │  │  • auto_router.py     (AI ticket routing)         │ │
    │  │  • sla_checker.py     (SLA monitoring)            │ │
    │  │  • sla_monitor.py     (Background job)            │ │
    │  │  • email.py           (Email notifications)       │ │
    │  └────────────────────────────────────────────────────┘ │
    │                                                           │
    │  ┌────────────────────────────────────────────────────┐ │
    │  │  Background Services (Threading)                   │ │
    │  │  ────────────────────────────────                  │ │
    │  │  • SLA Monitor Thread (checks every 5 sec)        │ │
    │  │    - Monitors ticket SLAs                         │ │
    │  │    - Updates status if breached                   │ │
    │  │    - Non-blocking (daemon thread)                 │ │
    │  └────────────────────────────────────────────────────┘ │
    │                                                           │
    │  Health Endpoints:                                       │
    │  • GET  /docs                (Swagger UI)              │
    │  • GET  /redoc               (ReDoc)                   │
    └──────────┬──────────────────────────────────────────────┘
               │
               ▼
    ┌──────────────────────────────────────────────────────────┐
    │      DATA PERSISTENCE LAYER                              │
    │      ──────────────────────────────────                  │
    │                                                           │
    │  ┌─────────────────────────────────────────────────────┐ │
    │  │  SQLAlchemy ORM (Object-Relational Mapping)       │ │
    │  │  ─────────────────────────────────────────        │ │
    │  │  Models:                                           │ │
    │  │  • User        (id, email, role, password hash)   │ │
    │  │  • Tenant      (id, name, industry)               │ │
    │  │  • Ticket      (id, title, status, priority...)   │ │
    │  │  • Comment     (id, text, user, ticket)           │ │
    │  │  • Provider    (id, name, skills, capacity)       │ │
    │  └─────────────────────────────────────────────────────┘ │
    │                                                           │
    │  ┌─────────────────────────────────────────────────────┐ │
    │  │  SQLite Database (Development)                    │ │
    │  │  ─────────────────────────────────────             │ │
    │  │  File: tickets.db                                  │ │
    │  │  Location: backend/tickets.db                      │ │
    │  │  Size: Auto-initialized, grows as data added      │ │
    │  │  Tables: users, tickets, comments, providers...   │ │
    │  │                                                    │ │
    │  │  ⚠️  For production: Switch to PostgreSQL         │ │
    │  └─────────────────────────────────────────────────────┘ │
    └──────────────────────────────────────────────────────────┘
```

---

## Request-Response Flow

### Example: User Login Workflow

```
1. USER INTERACTION (Frontend)
   └─ Clicks "Login" button
      └─ Enters: admin@hospital.com / admin123

2. FRONTEND VALIDATION
   └─ Checks email format
   └─ Checks password not empty
   └─ Shows loading spinner

3. API REQUEST (Axios)
   ├─ Method: POST
   ├─ URL: http://localhost:8000/auth/login
   ├─ Headers:
   │  └─ Content-Type: application/json
   └─ Body:
      ├─ email: "admin@hospital.com"
      └─ password: "admin123"

4. BACKEND PROCESSING (/auth/login endpoint)
   ├─ Receives request
   ├─ Finds user in database
   ├─ Verifies password using bcrypt
   ├─ Generates JWT token
   ├─ Returns response

5. API RESPONSE
   ├─ Status: 200 OK
   ├─ Headers:
   │  └─ Content-Type: application/json
   └─ Body:
      ├─ access_token: "eyJhbGc..."
      ├─ token_type: "bearer"
      ├─ user_id: 1
      ├─ role: "admin"
      └─ email: "admin@hospital.com"

6. FRONTEND PROCESSING
   ├─ Receives token
   ├─ Stores in localStorage
   ├─ Sets auth context
   ├─ Redirects to Dashboard
   └─ Hides loading spinner

7. SUBSEQUENT REQUESTS
   └─ All API calls include:
      ├─ Authorization: Bearer <token>
      └─ Backend validates token before responding
```

---

## Component Interaction Map

```
┌──────────────────────────────────────────────────────────────┐
│                    FRONTEND PAGES                            │
│  ──────────────────────────────────────────────────────────  │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐        │
│  │   Login     │  │  Dashboard  │  │   Tickets    │        │
│  │  Page       │→→│  Page       │→→│  List Page   │        │
│  │             │  │             │  │              │        │
│  └─────────────┘  └─────────────┘  └──────────────┘        │
│         ▲                ▼                 ▼                │
│         │          ┌──────────┐      ┌────────────┐        │
│         │          │  Navbar  │      │   Create   │        │
│         │          │Component │      │  Ticket    │        │
│         │          └──────────┘      │   Page     │        │
│         │               ▼            └────────────┘        │
│         │          ┌──────────┐            ▼               │
│         │          │ Sidebar  │      ┌───────────────┐     │
│         └──────────│Component │      │ Ticket Detail │     │
│                    └──────────┘      │ Page          │     │
│                          ▼                    ▼             │
│                    ┌─────────────┐    ┌──────────────┐     │
│                    │ Admin Panel │    │ Comments     │     │
│                    │ Page        │    │ Section      │     │
│                    └─────────────┘    └──────────────┘     │
│                                                              │
│  All Pages Share:                                           │
│  • Dark Mode Toggle (Navbar)                               │
│  • User Context (from Auth)                                │
│  • API Client (Axios)                                      │
└──────────────────────────────────────────────────────────────┘
                           ▼
              ┌────────────────────────────┐
              │   SHARED STATE & CONTEXT   │
              │  ──────────────────────    │
              │  • auth (user, token)     │
              │  • theme (dark/light)     │
              └────────────────────────────┘
```

---

## Data Models

### User Model
```
Field            | Type      | Description
─────────────────┼───────────┼──────────────────────────────
id               | Integer   | Primary key
email            | String    | Unique user email
password_hash    | String    | Bcrypt hashed password
role             | String    | admin, provider, user
tenant_id        | Integer   | FK to Tenant
created_at       | DateTime  | Creation timestamp
is_active        | Boolean   | Account status
```

### Ticket Model
```
Field            | Type      | Description
─────────────────┼───────────┼──────────────────────────────
id               | Integer   | Primary key
title            | String    | Ticket subject
description      | String    | Detailed description
status           | String    | open, in_progress, resolved, closed
priority         | String    | low, medium, high, urgent
assigned_to      | Integer   | FK to User (provider)
created_by       | Integer   | FK to User (creator)
tenant_id        | Integer   | FK to Tenant
created_at       | DateTime  | Creation timestamp
updated_at       | DateTime  | Last update timestamp
sla_deadline     | DateTime  | SLA deadline
```

### Comment Model
```
Field            | Type      | Description
─────────────────┼───────────┼──────────────────────────────
id               | Integer   | Primary key
text             | String    | Comment content
ticket_id        | Integer   | FK to Ticket
user_id          | Integer   | FK to User
created_at       | DateTime  | Creation timestamp
```

### Tenant Model
```
Field            | Type      | Description
─────────────────┼───────────┼──────────────────────────────
id               | Integer   | Primary key
name             | String    | Organization name
industry         | String    | Industry type
created_at       | DateTime  | Creation timestamp
```

---

## Key Features

### Authentication & Authorization
- **JWT-based authentication** with 30-minute token expiration
- **Role-based access control** (RBAC) with three tiers:
  - `admin`: Full system access, user management, SLA controls
  - `provider`: Ticket assignment, status updates, ticket resolution
  - `user`: Ticket creation, view own tickets, add comments
- **Password hashing** using bcrypt for security
- **Token validation** on every protected endpoint

### Ticket Management
- Create, read, update, delete (CRUD) operations
- **Status tracking**: open → in_progress → resolved → closed
- **Priority levels**: low, medium, high, urgent
- **Assignment system**: Admin assigns tickets to providers
- **Categorization**: Tickets can be categorized by type
- **Search and filtering**: Find tickets by title, status, priority, assignee
- **Ticket history**: View all updates and state changes

### AI-Powered Features
- **Intelligent routing**: Automatically suggest best provider based on skills
- **Priority prediction**: AI recommends priority level based on description
- **Category prediction**: AI suggests ticket category based on content

### SLA Monitoring
- **Automatic SLA tracking** for each ticket based on priority
- **Background monitoring thread** checks SLA status every 5 seconds
- **Breach notifications** when SLA is breached
- **Status updates**: Automatically marks tickets as "overdue" when SLA breached
- **Multi-tenant SLA policies**: Different SLA times per organization

### Multi-tenant Support
- **Organization isolation**: Each tenant sees only their data
- **Separate configurations**: Each organization has custom settings
- **Data segregation**: Database queries filtered by tenant_id
- **Customizable themes**: Per-tenant UI customization possible

### Communication
- **Comment threading**: Users can add comments to tickets
- **Email notifications** (ready to configure)
- **Real-time updates**: API reflects changes immediately
- **Audit trail**: All changes logged with timestamps

---

## Technology Stack

### Backend
| Technology | Purpose |
|-----------|---------|
| **Python 3** | Core language |
| **FastAPI** | Web framework, async support |
| **SQLAlchemy** | ORM for database operations |
| **SQLite** | Development database |
| **JWT (PyJWT)** | Authentication tokens |
| **Bcrypt** | Password hashing |
| **Uvicorn** | ASGI server |
| **Pydantic** | Data validation |

### Frontend
| Technology | Purpose |
|-----------|---------|
| **React 19** | UI library |
| **Material-UI (MUI)** | Component library |
| **Axios** | HTTP client |
| **React Router** | Navigation |
| **Chart.js** | Data visualization |
| **CSS3** | Styling |

### Database
| Technology | Purpose |
|-----------|---------|
| **SQLite** | Development database |
| **SQLAlchemy ORM** | Database abstraction |
| **Alembic** | Migration management (ready to use) |

---

## Design System

### Color Palette

#### Primary Colors
```
Primary Blue:       #667eea
Primary Purple:     #764ba2
Gradient:           linear-gradient(135deg, #667eea 0%, #764ba2 100%)
```

#### Secondary Colors
```
Pink Gradient:      #f093fb → #f5576c
Cyan Gradient:      #4facfe → #00f2fe
Warm Gradient:      #fa709a → #fee140
```

#### Neutral Colors
```
Text Dark:          #333
Text Light:         #e0e0e0
Background Light:   #f5f7fa
Background Dark:    #1a1a1a
Secondary Dark:     #2d2d2d
Border:             #e0e0e0
Disabled:           #999
```

#### Status Colors
```
Success/Low:        #4caf50 (Green)
Warning/Medium:     #ff9800 (Orange)
Error/High:         #e53935 (Red)
Info:               #1976d2 (Blue)
```

### Typography

#### Headings
```
H1 (Page Title):    32px, weight 700, letter-spacing -1px
H2 (Section):       24px, weight 700
H3 (Subsection):    20px, weight 700
H4 (Card Title):    18px, weight 600
H5 (Label):         14px, weight 600
H6 (Small):         12px, weight 600, text-transform uppercase
```

#### Body Text
```
Body Large:         16px, weight 400, line-height 1.6
Body Medium:        14px, weight 400, line-height 1.5
Body Small:         12px, weight 400, line-height 1.5
Font Family:        -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto'
```

### Spacing System (8px Base)
```
xs:  4px
sm:  8px
md:  16px
lg:  24px
xl:  32px
2xl: 40px
```

### Shadow System
```
Depth 1 (subtle):   0 2px 8px rgba(0,0,0,0.08)
Depth 2 (medium):   0 4px 12px rgba(0,0,0,0.12)
Depth 3 (strong):   0 8px 24px rgba(0,0,0,0.15)
Depth 4 (emphasis): 0 16px 40px rgba(0,0,0,0.20)
```

---

## Security Considerations

1. **Password Security**: All passwords are hashed with bcrypt, never stored in plain text
2. **JWT Tokens**: Tokens are short-lived (30 minutes) and validated on every protected request
3. **CORS Policy**: Configured to accept requests only from frontend origin
4. **Input Validation**: Pydantic schemas validate all incoming data
5. **SQL Injection Prevention**: SQLAlchemy parameterized queries prevent SQL injection
6. **Role-Based Access**: Endpoints check user role before processing requests
7. **Tenant Isolation**: All queries include tenant_id filter to prevent data leakage

---

## Deployment Considerations

### Development
- SQLite database is suitable for development and testing
- Auto-reload enabled for rapid development iteration
- Debug mode can be enabled for detailed error information

### Production
- **Database**: Switch to PostgreSQL or MySQL for better scalability
- **Server**: Use production-grade ASGI server (Gunicorn with Uvicorn workers)
- **Frontend**: Build and serve static files through CDN or reverse proxy
- **Environment Variables**: Store secrets in environment files, never commit them
- **HTTPS**: Enable SSL/TLS certificates
- **Monitoring**: Set up logging and error tracking (Sentry, etc.)
- **Database Backups**: Implement regular backup strategy
- **Rate Limiting**: Add rate limiting to API endpoints
- **CORS**: Configure for production domain only

---

## Performance Optimization

- **Lazy Loading**: Frontend components use code splitting
- **Database Indexing**: Key fields indexed for faster queries
- **Background Jobs**: SLA monitoring runs in separate thread
- **Caching**: Frontend caches API responses where appropriate
- **API Documentation**: Auto-generated Swagger UI for reference

---

## Future Enhancement Ideas

1. **WebSocket Support**: Real-time notifications for ticket updates
2. **Advanced Analytics**: Dashboards showing metrics and trends
3. **Integration APIs**: Connect with third-party services
4. **Workflow Automation**: Automated ticket workflows
5. **Mobile App**: Native mobile clients for iOS/Android
6. **Chat Integration**: Slack, Teams, or other chat platform integration
7. **Advanced AI**: ML models for better ticket routing and categorization
8. **Knowledge Base**: Self-service portal for common issues
9. **Reporting**: Custom report generation
10. **API Rate Limiting**: Protect against abuse


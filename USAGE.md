# AI Ticketing System - Usage Guide

## Quick Start

### Option 1: Automatic Startup (Recommended)
```powershell
cd c:\Users\dheer\OneDrive\Desktop\PROJECT1
.\start.ps1
```
✅ Automatically installs dependencies, starts both services, and displays URLs

### Option 2: Manual Setup

#### Step 1: Start Backend
```powershell
# Open PowerShell Window 1
cd c:\Users\dheer\OneDrive\Desktop\PROJECT1\ai-ticketing-system\backend

# Create virtual environment (first time only)
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Start backend server
uvicorn app.main:app --reload --port 8000
```

#### Step 2: Start Frontend
```powershell
# Open PowerShell Window 2
cd c:\Users\dheer\OneDrive\Desktop\PROJECT1\ai-ticketing-system\frontend

# Install dependencies (first time only)
npm install

# Start frontend
npm start
```

---

## Accessing the Application

Once both services are running, open these URLs in your browser:

| Service | URL | Purpose |
|---------|-----|---------|
| **Frontend** | http://localhost:3000 | Main application UI |
| **API Docs** | http://localhost:8000/docs | Interactive API testing |
| **API ReDoc** | http://localhost:8000/redoc | Alternative API documentation |
| **Backend API** | http://localhost:8000 | API endpoint (REST calls) |

---

## Login Credentials

Pre-seeded demo users are automatically created in the database:

### Admin Account
```
Email:    admin@hospital.com
Password: admin123
Access:   Full system access, user management, SLA controls
```

### Support Provider Account
```
Email:    provider@hospital.com
Password: provider123
Access:   Assign tickets, resolve tickets, update status
```

### Regular User Account
```
Email:    user@hospital.com
Password: user123
Access:   Create tickets, view own tickets, add comments
```

---

## System Features

### 1. Dashboard
- View system overview
- See ticket statistics
- Monitor active tickets
- Access quick actions

### 2. Ticket Management
- **Create Tickets**: Submit new support requests
- **View Tickets**: See all tickets (filtered by role)
- **Update Status**: Change ticket status (open → in-progress → resolved → closed)
- **Set Priority**: Assign priority levels (low, medium, high, urgent)
- **Assign Tickets**: (Admin/Provider) Assign to support staff
- **Add Comments**: Collaborate with team members

### 3. User Management (Admin Only)
- View all users
- Create new users
- Manage user roles (admin, provider, user)
- Disable/enable user accounts

### 4. AI Features
- **Intelligent Routing**: System suggests best provider for each ticket
- **Priority Prediction**: AI recommends priority based on description
- **Category Suggestion**: Auto-suggests ticket category

### 5. SLA Monitoring
- Automatic SLA tracking for every ticket
- Real-time breach detection
- Breach notifications
- Visual indicators for overdue tickets

### 6. Dark Mode
- Toggle dark/light mode in navbar
- Persistent preference
- Smooth transitions

---

## User Workflows

### For End Users

#### Creating a Ticket
1. Login with user credentials
2. Navigate to "Create Ticket" page
3. Fill in:
   - **Title**: Brief description of the issue
   - **Description**: Detailed explanation
   - **Category**: Select relevant category (optional - AI will suggest)
   - **Priority**: Select priority level (optional - AI will suggest)
4. Click "Submit Ticket"
5. Track ticket status in "My Tickets"

#### Tracking Your Tickets
1. Go to "My Tickets" page
2. View all tickets you created
3. Click on any ticket to see details
4. Add comments to collaborate
5. View comments from support team

---

### For Support Providers

#### Assigning Tickets
1. Login with provider credentials
2. Go to "Provider Tickets" page
3. See unassigned tickets
4. Assign tickets to yourself or other providers

#### Working on Tickets
1. Go to "My Assigned Tickets"
2. Click on a ticket to view details
3. Update ticket status as you work
4. Add comments to communicate with team
5. Mark as resolved when done

#### SLA Monitoring
- Red indicator: SLA breached
- Yellow indicator: SLA approaching
- Green indicator: Within SLA

---

### For Administrators

#### Managing Users
1. Go to "Admin Panel"
2. Select "User Management"
3. View all users
4. Create new users
5. Edit user roles and permissions
6. Deactivate users if needed

#### System Configuration
1. Access admin settings
2. Configure SLA policies
3. Set up email notifications
4. Manage tenant settings
5. View system logs

#### Monitoring
1. Check "Dashboard" for system health
2. View ticket statistics
3. Monitor SLA breaches
4. Review system performance

---

## Common Tasks

### How to Update Ticket Status
1. Open the ticket
2. Click on Status dropdown
3. Select new status:
   - **Open**: Initial state when ticket is created
   - **In Progress**: When work has started
   - **Resolved**: When issue is fixed
   - **Closed**: When ticket is finalized
4. Changes save automatically

### How to Assign a Ticket
1. Open the ticket (Admin/Provider only)
2. Click on "Assign To" field
3. Select a provider from the list
4. Save - ticket is now assigned

### How to Change Priority
1. Open the ticket
2. Click on Priority dropdown
3. Select new priority:
   - **Low**: Non-urgent issues
   - **Medium**: Standard requests
   - **High**: Important matters
   - **Urgent**: Critical issues
4. Changes reflect in the system immediately

### How to Add a Comment
1. Open the ticket
2. Scroll to "Comments" section
3. Type your comment
4. Click "Post Comment"
5. Comment appears immediately with timestamp

### How to Search Tickets
1. Go to "Tickets" page
2. Use search bar at top
3. Search by:
   - Ticket title
   - Ticket ID
   - Status
   - Priority
   - Assignee

---

## Troubleshooting

### Backend Won't Start
```powershell
# Check if port 8000 is in use
netstat -ano | findstr :8000

# Kill the process using port 8000
taskkill /PID <PID> /F

# Try starting again
uvicorn app.main:app --reload --port 8000
```

### Frontend Won't Start
```powershell
# Clear npm cache
npm cache clean --force

# Delete node_modules and reinstall
rm -r node_modules
npm install

# Try starting again
npm start
```

### Can't Login
1. Check credentials match demo users (see "Login Credentials" above)
2. Verify backend is running (check http://localhost:8000/docs)
3. Check browser console for errors (F12)
4. Clear browser cache and cookies
5. Try in a different browser

### Database Issues
```powershell
# Reset database (WARNING: deletes all data)
cd backend
rm tickets.db
python -c "from app.db.init_db import init_db; init_db()"
```

### Port Already in Use
```powershell
# Find process using port
netstat -ano | findstr :8000  # For backend
netstat -ano | findstr :3000  # For frontend

# Kill the process
taskkill /PID <process_id> /F
```

### CORS Errors
- Ensure frontend is at http://localhost:3000
- Ensure backend is at http://localhost:8000
- Restart both services
- Clear browser cache

---

## Performance Tips

### For Better Performance
1. **Close unnecessary browser tabs** - reduces memory usage
2. **Use Chrome/Edge** - better performance than Firefox
3. **Clear cache regularly** - prevents outdated data
4. **Upgrade Python** - use Python 3.9 or newer
5. **Use SSD** - faster database operations

### Database Maintenance
```powershell
# Optimize database
cd backend
python -c "from app.db.database import engine; engine.execute('VACUUM')"
```

---

## Deployment for Streamlit

### Prerequisites
- Python 3.9+
- All backend dependencies installed
- Frontend built as static files
- Database initialized

### Steps to Deploy on Streamlit Cloud

1. **Build Frontend**
```powershell
cd ai-ticketing-system\frontend
npm run build
```
The built files are in `build/` directory.

2. **Prepare Backend Files**
- Keep entire `backend/` folder
- Keep `requirements.txt`
- Keep database file (or let it auto-initialize)

3. **Create Streamlit App** (optional wrapper)
- Create `streamlit_app.py` in root
- Use to serve frontend and manage backend

4. **Push to GitHub**
```powershell
git add .
git commit -m "Ready for Streamlit deployment"
git push origin main
```

5. **Deploy on Streamlit Cloud**
- Go to https://streamlit.io/cloud
- Connect your GitHub repository
- Select branch (main)
- Set main file to `streamlit_app.py` or appropriate startup file
- Click "Deploy"

### Production Checklist
- [ ] Environment variables configured
- [ ] Database backed up
- [ ] CORS configured for production URL
- [ ] Frontend built and optimized
- [ ] Backend dependencies locked
- [ ] Error logging enabled
- [ ] Rate limiting configured
- [ ] HTTPS enabled
- [ ] Monitoring set up
- [ ] Backups scheduled

---

## Additional Resources

### API Documentation
Visit http://localhost:8000/docs for interactive Swagger UI where you can:
- Test all API endpoints
- See request/response formats
- Try different parameters
- View error responses

### Code Structure
```
ai-ticketing-system/
├── backend/
│   ├── app/
│   │   ├── routers/           # API endpoints
│   │   ├── services/          # Business logic
│   │   ├── db/               # Database models
│   │   ├── auth/             # Authentication
│   │   ├── schemas/          # Data validation
│   │   └── main.py           # App entry point
│   ├── requirements.txt        # Python dependencies
│   └── venv/                   # Virtual environment
│
├── frontend/
│   ├── src/
│   │   ├── pages/            # Page components
│   │   ├── components/       # Reusable components
│   │   ├── api/             # API client
│   │   ├── context/         # State management
│   │   └── App.js           # Root component
│   ├── package.json          # npm dependencies
│   └── public/              # Static files
│
└── ml_training/              # AI model files
```

### Environment Variables (Backend)
Create `.env` file in backend directory:
```
DATABASE_URL=sqlite:///./tickets.db
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

---

## Support

For issues or questions:
1. Check this guide first
2. Review API documentation at http://localhost:8000/docs
3. Check browser console (F12) for errors
4. Check backend logs in terminal
5. Check database status with `PRAGMA integrity_check;`


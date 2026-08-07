"""
AI Ticketing System - Streamlit Deployment Wrapper

This file serves as the entry point for Streamlit Cloud deployment.
It manages the backend API server and provides frontend UI integration.
"""

import streamlit as st
import subprocess
import time
import requests
import os
from pathlib import Path

# Page configuration
st.set_page_config(
    page_title="AI Ticketing System",
    page_icon="🎫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Styling
st.markdown("""
    <style>
    .main {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    </style>
    """, unsafe_allow_html=True)

# Backend URL configuration
BACKEND_PORT = 8000
BACKEND_URL = f"http://localhost:{BACKEND_PORT}"
PROJECT_ROOT = Path(__file__).parent
BACKEND_DIR = PROJECT_ROOT / "ai-ticketing-system" / "backend"

@st.cache_resource
def start_backend():
    """Start the FastAPI backend server"""
    try:
        # Check if backend is already running
        response = requests.get(f"{BACKEND_URL}/docs", timeout=2)
        if response.status_code == 200:
            return True, "Backend is already running"
    except:
        pass
    
    # Start backend in background
    try:
        cmd = f"cd {BACKEND_DIR} && python -m uvicorn app.main:app --host 0.0.0.0 --port {BACKEND_PORT}"
        subprocess.Popen(cmd, shell=True)
        time.sleep(3)  # Wait for startup
        
        # Verify backend started
        response = requests.get(f"{BACKEND_URL}/docs", timeout=5)
        return True, "Backend started successfully"
    except Exception as e:
        return False, f"Failed to start backend: {str(e)}"

# Main UI
st.title("🎫 AI Ticketing System")
st.markdown("---")

# Sidebar
with st.sidebar:
    st.header("Navigation")
    page = st.radio(
        "Select a page:",
        ["📊 Dashboard", "🎫 Tickets", "👥 Users", "⚙️ Admin", "ℹ️ About"]
    )
    
    st.markdown("---")
    st.subheader("Documentation")
    st.markdown("""
    - **[THEORY.md](https://github.com/your-repo/blob/main/THEORY.md)**: System architecture & technical details
    - **[USAGE.md](https://github.com/your-repo/blob/main/USAGE.md)**: How to use & setup instructions
    """)

# Page content
if page == "📊 Dashboard":
    st.subheader("Dashboard")
    st.info("Dashboard page - Real-time system overview and statistics")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Tickets", "142", "↑ 12")
    with col2:
        st.metric("Open Tickets", "35", "↓ 2")
    with col3:
        st.metric("SLA Compliance", "94%", "↑ 3%")

elif page == "🎫 Tickets":
    st.subheader("Ticket Management")
    st.info("View, create, and manage support tickets")
    
    tab1, tab2, tab3 = st.tabs(["View Tickets", "Create Ticket", "My Tickets"])
    
    with tab1:
        st.write("Displaying all tickets...")
    
    with tab2:
        st.write("Create a new ticket form")
    
    with tab3:
        st.write("Your tickets")

elif page == "👥 Users":
    st.subheader("User Management")
    st.info("Manage system users and roles")
    st.write("User management interface")

elif page == "⚙️ Admin":
    st.subheader("Administration")
    st.info("System administration panel")
    
    admin_tab1, admin_tab2, admin_tab3 = st.tabs(["Users", "Settings", "SLA Policies"])
    
    with admin_tab1:
        st.write("User administration")
    
    with admin_tab2:
        st.write("System settings")
    
    with admin_tab3:
        st.write("SLA policy configuration")

elif page == "ℹ️ About":
    st.subheader("About This System")
    
    st.markdown("""
    ## AI Ticketing System
    
    A modern, full-stack ticketing platform with AI-powered features for intelligent
    ticket routing and SLA monitoring.
    
    ### Quick Stats
    - **Frontend**: React 19 with Material-UI
    - **Backend**: FastAPI with Python
    - **Database**: SQLite (dev) / PostgreSQL (production)
    - **Features**: JWT Auth, Multi-tenant, AI Routing, SLA Monitoring
    
    ### Demo Credentials
    - **Admin**: admin@hospital.com / admin123
    - **Provider**: provider@hospital.com / provider123
    - **User**: user@hospital.com / user123
    
    ### Documentation
    - **[THEORY.md](THEORY.md)**: Complete technical documentation
    - **[USAGE.md](USAGE.md)**: Setup and usage guide
    
    ### Links
    - [Backend API Docs](http://localhost:8000/docs)
    - [Full Frontend Application](http://localhost:3000)
    """)

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.85rem;">
    <p>AI Ticketing System | Built with FastAPI, React & Streamlit</p>
    <p>For full application, visit <a href="http://localhost:3000">localhost:3000</a></p>
</div>
""", unsafe_allow_html=True)

# Disaster Logistics Response Management System

A web-based disaster logistics response management system built using **Flask**, **SQLite**, and **Flask-Login**. 
This system allows operators to track disaster reports, assign teams, and monitor ongoing emergency responses in real-time. 
It also supports multiple user roles with role-specific permissions.

---

## Table of Contents

- [Features](#features)  
- [User Roles](#user-roles)  
- [Technologies](#technologies)  
- [Installation](#installation)  
- [Usage](#usage)  
- [Database Setup](#database-setup)  
- [API Endpoints](#api-endpoints)  
- [License](#license)  

---

## Features

- **User Authentication:** Login system with different roles and permissions.
- **Dashboard:** Overview of active, pending, and resolved disaster reports.
- **Report Management:** Create, edit, and track disaster reports.
- **Team Management:** Monitor team availability, assignments, and statuses.
- **Real-Time Monitoring:** Live data feed for responders.
- **Profile Settings:** Update user details like name and phone.
- **Severity-Based Prioritization:** Automatic priority assignment based on severity.

---

## User Roles

| Role        | Description |
|------------|-------------|
| **Programmer** | System administrator or developer for maintenance. |
| **Admin**      | Manages users, teams, and high-level system settings. |
| **Operator**   | Handles disaster report creation and team assignment. |
| **Responder**  | Receives assigned tasks and updates disaster status. |

---

## Technologies

- **Python 3.x**  
- **Flask** – Web framework  
- **Flask-Login** – User session management  
- **SQLite** – Lightweight database  
- **Jinja2** – Templating engine for HTML pages  
- **HTML/CSS/JS** – Frontend rendering  

---

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/czrnaa/thesis-visio-codicis.git
   cd thesis-visio-codicis

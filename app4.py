from flask import Flask, flash, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit  # for real-time updates
import mysql.connector  # used to connect to MySQL database
from mysql.connector import Error
from datetime import datetime
from haversine import haversine
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import matplotlib.pyplot as plt
from io import BytesIO
import base64
from collections import defaultdict

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Necessary for session management
socketio = SocketIO(app)
CORS(app)

# MySQL database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',  # replace with your MySQL username
    'password': '',  # replace with your MySQL password
    'database': 'q-buddy-main'  # replace with your MySQL database name
}

# Hardcoded venue location for location-based queue joining
venue_lat = -1.2640637
venue_lon = 36.9077355

# Office codes for different services
office_codes = {
    'General Consultation': 'GC',
    'Dental': 'DT',
    'Dermatologist': 'DE',
    'Labaratory': 'LA',
    'Emergency Room': 'ER'
}

# Counter for ticket numbers
office_counters = {
    'GC': 1,
    'DT': 1,
    'LA': 1,
    'ER': 1
}

def create_connection():
    """Create a MySQL database connection."""
    try:
        conn = mysql.connector.connect(**db_config)
        if conn.is_connected():
            return conn
    except Error as e:
        print(f"Error: {e}")
    return None

@app.route('/')
def index():
    return render_template('index.html')

# Staff login route
@app.route('/login_staff', methods=['GET', 'POST'])
def login_staff():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = create_connection()
        if conn is None:
            flash("Database connection failed!", "error")
            return redirect(url_for('login_staff'))

        try:
            cursor = conn.cursor()

            # Check if the user exists in the 'staff' table (registered staff)
            cursor.execute("SELECT email, password, office FROM staff WHERE email = %s", (email,))
            staff = cursor.fetchone()

            if staff:
                # User exists, now check if the password matches
                stored_password, staff_office = staff[1], staff[2]  # Fetch hashed password and office
                if check_password_hash(stored_password, password):
                    # Password matches, log the login attempt
                    session['email'] = email
                    session['office'] = staff_office  # Store the staff office in session
                    flash("Login successful!", "success")
                    return redirect(url_for('staff_dashboard'))

                else:
                    flash("Invalid password. Please try again.", "error")
                    return redirect(url_for('login_staff'))

            else:
                flash("This email is not registered. Please register first.", "error")
                return redirect(url_for('register_staff'))

        except Error as e:
            flash(f"Error: {e}", "error")
            return redirect(url_for('login_staff'))

        finally:
            cursor.close()
            conn.close()

    return render_template('login.html')

# Staff dashboard where they only see tickets for their office
@app.route('/staff_dashboard')
def staff_dashboard():
    if 'office' in session:
        staff_office = session['office']

        conn = create_connection()
        cursor = conn.cursor()

        # Only fetch tickets for the staff's assigned office
        cursor.execute("SELECT * FROM queues WHERE ticket_number LIKE %s AND processed = 0 ORDER BY id", (staff_office + '%',))
        tickets = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template('queue-screen.html', tickets=tickets, office=staff_office)
    else:
        flash("Please log in to access the dashboard.", "error")
        return redirect(url_for('login_staff'))

# Route for user to get real-time updates on their ticket and queue status
@app.route('/ticket_status/<ticket_number>')
def ticket_status(ticket_number):
    try:
        conn = create_connection()
        cursor = conn.cursor()

        # Fetch the number of people ahead in the queue
        cursor.execute("SELECT COUNT(*) FROM queues WHERE ticket_number < %s AND processed = FALSE AND ticket_number LIKE %s", 
                       (ticket_number, ticket_number[:2] + '%'))
        position = cursor.fetchone()[0]

        cursor.close()
        conn.close()
    except Error as e:
        print(f"Error: {e}")
        position = None

    return render_template('status.html', ticket_number=ticket_number, position=position)

# Real-time updates for users
@socketio.on('request_queue_update')
def handle_queue_update(ticket_number):
    conn = create_connection()
    cursor = conn.cursor()

    # Continuously fetch the current serving ticket and the user's position in the queue
    while True:
        try:
            # Get the current ticket being served for the user's office
            office_code = ticket_number[:2]
            cursor.execute("SELECT ticket_number FROM queues WHERE ticket_number LIKE %s AND processed = FALSE ORDER BY id LIMIT 1", (office_code + '%',))
            current_ticket = cursor.fetchone()

            if current_ticket:
                current_ticket = current_ticket[0]
            else:
                current_ticket = 'None'

            # Get the user's position in the queue
            cursor.execute("SELECT COUNT(*) FROM queues WHERE ticket_number < %s AND processed = FALSE AND ticket_number LIKE %s", 
                           (ticket_number, office_code + '%'))
            position = cursor.fetchone()[0]

            # Emit the real-time updates
            emit('queue_status_update', {'current_ticket': current_ticket, 'position': position})
            socketio.sleep(5)  # Send updates every 5 seconds

        except Error as e:
            print(f"Error: {e}")
            break

        finally:
            cursor.close()
            conn.close()
@app.route('/queue-screen', methods=['GET', 'POST'])
def queue_screen():
    conn = create_connection()
    cursor = conn.cursor()

    # Fetch the current ticket (the first unprocessed one)
    cursor.execute("SELECT id, ticket_number FROM queues2 WHERE processed = 0 ORDER BY id LIMIT 1")
    current_ticket = cursor.fetchone()

    # Fetch the next ticket in the queue
    if current_ticket:
        cursor.execute("SELECT ticket_number FROM queues2 WHERE processed = 0 AND id > %s ORDER BY id LIMIT 1", (current_ticket[0],))
        next_ticket = cursor.fetchone()
    else:
        next_ticket = None

    cursor.close()
    conn.close()

    return render_template('queue-screen.html', current_ticket=current_ticket, next_ticket=next_ticket)
           
@app.route('/process_ticket', methods=['POST'])
def process_ticket():
    try:
        conn = create_connection()
        cursor = conn.cursor()

        # Fetch the first unprocessed ticket from the queues2 table
        cursor.execute(
            "SELECT id, user_id, name, ticket_number, institution, room FROM queues2 WHERE processed = FALSE ORDER BY id ASC LIMIT 1"
        )
        current_ticket = cursor.fetchone()

        if current_ticket:
            ticket_id = current_ticket[0]
            user_id = current_ticket[1]
            name = current_ticket[2]
            ticket_number = current_ticket[3]
            institution = current_ticket[4]
            room = current_ticket[5]

            # Mark the ticket as processed by setting processed to TRUE
            cursor.execute("UPDATE queues2 SET processed = TRUE WHERE id = %s", (ticket_id,))

            # Move the processed ticket to the served2 table
            cursor.execute(
                "INSERT INTO served2 (user_id, name, ticket_number, institution, room, served_at) "
                "VALUES (%s, %s, %s, %s, %s, NOW())", 
                (user_id, name, ticket_number, institution, room)
            )

            # Delete the processed ticket from queues2
            cursor.execute("DELETE FROM queues2 WHERE id = %s", (ticket_id,))

            # Commit the changes to the database
            conn.commit()

            # Notify clients about the queue update (if using Socket.IO)
            socketio.emit('update_queue')

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Error: {e}")
        flash("An error occurred while processing the ticket.", "error")
    
    return redirect(url_for('queue_screen'))
@app.route('/skip/<int:id>', methods=['POST'])
def skip_ticket(id):
    conn = create_connection()
    cursor = conn.cursor()

    # Move the skipped ticket to the skipped table
    cursor.execute("SELECT name,ticket_number, user_id FROM queues WHERE id = %s", (id,))
    skipped_ticket = cursor.fetchone()

    if skipped_ticket:
        cursor.execute("INSERT INTO skipped (ticket_number, user_id, reason) VALUES (%s, %s, %s)", (skipped_ticket[0], skipped_ticket[1], 'Skipped'))

        # Remove from the queues table
        cursor.execute("DELETE FROM queues WHERE id = %s", (id,))
        conn.commit()

    cursor.close()
    conn.close()

    return redirect(url_for('queue_screen'))
if __name__ == '__main__':
    socketio.run(app, debug=True)

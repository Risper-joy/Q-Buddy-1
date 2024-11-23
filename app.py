from flask import Flask, flash, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, emit # for real-time updates
import mysql.connector # used to connect to MySQL database
from mysql.connector import Error
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Necessary for session management
socketio = SocketIO(app)

# MySQL database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',  # replace with your MySQL username
    'password': '',  # replace with your MySQL password
    'database': 'q-buddy-main'  # replace with your MySQL database name
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/handle_button_click', methods=['POST'])
def handle_button_click():
    action = request.form['action']
    if action == 'register':
        return redirect(url_for('register'))
    elif action == 'join_remotely':
        return redirect(url_for('join_remotely'))

@app.route('/register')
def register():
    return render_template('Registration.html')

@app.route('/join_remotely')
def join_remotely():
    return render_template('join_remotely.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html', office_codes=office_codes)  # Render the dashboard page with office codes

@app.route('/submit', methods=['POST'])
def submit():
    if request.method == 'POST':
        name = request.form['name']
        reg_no = request.form['reg-no']
        institution = request.form['institution']
        registration_time = datetime.utcnow()  # Capture the current UTC time

        # Create a connection to the database
        conn = create_connection()
        if conn is None:
            flash("Database connection failed!", "error")
            return redirect(url_for('register'))

        try:
            cursor = conn.cursor()
            insert_query = """
            INSERT INTO users2 (name, reg_no, institution, registration_time)
            VALUES (%s, %s, %s, %s)
            """
            cursor.execute(insert_query, (name, reg_no, institution, registration_time))
            conn.commit()

            flash("Registration successful!", "success")
            return redirect(url_for('dashboard'))

        except Error as e:
            flash(f"Error while inserting data: {e}", "error")
            conn.rollback()
            return redirect(url_for('register'))

        finally:
            cursor.close()
            conn.close()

@app.route('/generate_ticket', methods=['POST'])
def generate_ticket():
    office_code = request.form['office_code']
    ticket_number = f"{office_code}{office_counters[office_code]:03d}"  # Format as 3-digit number with leading zeros
    office_counters[office_code] += 1
    
    try:
        conn = create_connection()
        cursor = conn.cursor()
        
        # Fetch the most recent user
        cursor.execute("SELECT id, name FROM users2 ORDER BY id DESC LIMIT 1")
        user = cursor.fetchone()
        
        if user:
            user_id, name = user
            cursor.execute("INSERT INTO queues (user_id, name, ticket_number, processed) VALUES (%s, %s, %s, %s)", 
                           (user_id, name, ticket_number, False))
            conn.commit()
           # Fetch the created_at timestamp of the inserted ticket
            cursor.execute(
                "SELECT created_at FROM queues WHERE ticket_number = %s ORDER BY id DESC LIMIT 1", 
                (ticket_number,)
            )
            created_at = cursor.fetchone()[0]
            # Format the timestamp if needed
        created_at = created_at.strftime('%Y-%m-%d %H:%M:%S')

        cursor.close()
        conn.close()
    except Error as e:
        print(f"Error: {e}")
    
    return render_template('tickets.html', ticket_number=ticket_number,created_at=created_at)
@app.route('/view_queues')
def view_queues():
    conn = create_connection()
    cursor = conn.cursor()

    try:
        # Fetch all records from the 'queues' table
        cursor.execute("SELECT * FROM queues2")
        queues2 = cursor.fetchall()  # Fetch all rows
        
        # Optional: Define column headers based on your table structure
        column_names = [i[0] for i in cursor.description]  # Get column headers

    except Error as e:
        print(f"Error fetching data: {e}")
        queues = []  # Return empty list if there's an error

    finally:
        cursor.close()
        conn.close()

    # Pass the fetched records to the front-end template
    return render_template('queue-list2.html', queues=queues, columns=column_names)

if __name__ == '__main__':
    socketio.run(app, debug=True)

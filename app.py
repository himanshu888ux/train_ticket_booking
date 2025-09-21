from flask import Flask, render_template, jsonify, request, flash, redirect, url_for, session
import mysql.connector
import google.generativeai as genai
import json
from datetime import datetime, date, timedelta


from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.units import inch
import io
from flask import send_file

app = Flask(__name__)
app.secret_key = 'hidhsifkdfjjsjkfnjk'

# Add a template global for current date
@app.template_global()
def current_date():
    return date.today().strftime('%Y-%m-%d')

db_config = {
    'host': 'localhost',
    'user': 'root',  
    'password': '', 
    'database': 'railway_booking'
}

def get_db_connection():
    try:
        conn = mysql.connector.connect(**db_config)
        return conn
    except mysql.connector.Error as e:
        print(f"Database connection error: {e}")
        return None

genai.configure(api_key="AIzaSyC0UsJBioAi2DWXDMcYFQP0ri5tujZrADI")
model = genai.GenerativeModel("gemini-1.5-flash")

@app.route('/')
def index():
    # Check if user is logged in, if not redirect to login
    if 'email' not in session:
        flash('Please login to access the website', 'warning')
        return redirect(url_for('login'))
    
    # Fetch popular trains from database
    conn = get_db_connection()
    popular_trains = []
    
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            # Get 3 popular trains (you can modify this query as needed)
            cursor.execute("SELECT * FROM trains ORDER BY available_seats DESC LIMIT 3")
            popular_trains = cursor.fetchall()
            
            # Calculate duration for each train
            for train in popular_trains:
                if train['departure_time'] and train['arrival_time']:
                    # Convert string times to datetime objects if needed
                    if isinstance(train['departure_time'], str):
                        dep_time = datetime.strptime(str(train['departure_time']), '%H:%M:%S')
                        arr_time = datetime.strptime(str(train['arrival_time']), '%H:%M:%S')
                    else:
                        dep_time = train['departure_time']
                        arr_time = train['arrival_time']
                    
                    # Calculate duration
                    duration = arr_time - dep_time
                    # Handle overnight journeys (negative duration)
                    if duration.total_seconds() < 0:
                        duration = timedelta(days=1) + duration
                    
                    # Convert to hours and minutes
                    total_seconds = duration.total_seconds()
                    hours = int(total_seconds // 3600)
                    minutes = int((total_seconds % 3600) // 60)
                    train['duration'] = f"{hours}h {minutes}m"
                else:
                    train['duration'] = "N/A"
            
            cursor.close()
        except Exception as e:
            print(f"Error fetching trains: {e}")
        finally:
            conn.close()
    
    # Since we know user is logged in, get user info
    email = session['email']
    conn = get_db_connection()
    if not conn:
        flash('Database connection failed', 'danger')
        return render_template('index.html', popular_trains=popular_trains)
    
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    
    if user:
        # Pass only the user's name, not the entire dictionary
        return render_template('index.html', user=user['name'], popular_trains=popular_trains)
    else:
        # User not found in database, clear session and redirect to login
        session.clear()
        flash('User session expired. Please login again.', 'warning')
        return redirect(url_for('login'))

@app.route("/login")
def login():
    return render_template('login.html')

@app.route('/login-process', methods=['POST'])
def login_process():
    email = request.form['email']
    password = request.form['password']

    conn = get_db_connection()
    if not conn:
        flash('Database connection failed', 'danger')
        return render_template('login.html')
    
    cursor = conn.cursor(dictionary=True)
    query = "SELECT * FROM users WHERE email = %s AND password = %s"
    cursor.execute(query, (email, password))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if user:
        session['email'] = email
        session['name'] = user['name']
        session['user_id'] = user['id']  # Add user_id to session
        return redirect(url_for('index'))
    else:
        error_message = "Invalid email or password"
        return render_template('login.html', error=error_message)

@app.route("/signup")
def signup():
    return render_template('signup.html')

@app.route('/signup_process', methods=["POST"])
def signup_process():
    name = request.form['name']
    email = request.form['email']
    password = request.form['password']
    conn = get_db_connection()
    
    if not conn:
        flash('Database connection failed', 'danger')
        return redirect(url_for('signup'))
    
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        if user:
            flash('Email already registered', 'danger')
            return redirect(url_for('signup'))
       
        cursor.execute("INSERT INTO users (name, email, password) VALUES (%s, %s, %s)", (name, email, password))
        conn.commit()
        flash('Signup successful! Please log in.', 'success')
        return redirect(url_for('login'))
    except Exception as e:
        conn.rollback() 
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('signup'))
    finally:
        cursor.close()
        conn.close()

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route("/about")
def about():
    return render_template('about.html')

@app.route("/contact-us")
def contact_us():
    return render_template('contact-us.html')

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'email' not in session:
        return redirect(url_for('login')) 

    email = session['email']
    conn = get_db_connection()
    if not conn:
        flash('Database connection failed', 'danger')
        return redirect(url_for('index'))
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    
    if not user:
        cursor.close()
        conn.close()
        session.clear()
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if old_password != user['password']:
            flash('Old password is incorrect', 'danger')
            cursor.close()
            conn.close()
            return redirect(url_for('profile'))

        if new_password != confirm_password:
            flash('New passwords do not match', 'danger')
            cursor.close()
            conn.close()
            return redirect(url_for('profile'))

        cursor.execute("UPDATE users SET password = %s WHERE email = %s", (new_password, email))
        conn.commit()
        flash('Password updated successfully', 'success')
        cursor.close()
        conn.close()
        return redirect(url_for('profile'))

    cursor.close()
    conn.close()
    return render_template('profile.html', user=user)

@app.route("/reviews")
def reviews():
    return render_template("reviews.html")

# New train searching and booking functionality
@app.route("/search_trains", methods=['POST'])
def search_trains():
    if 'user_id' not in session:
        flash('Please login to search trains', 'warning')
        return redirect(url_for('login'))
    
    source = request.form['source']
    destination = request.form['destination']
    journey_date = request.form['date']
    
    conn = get_db_connection()
    if not conn:
        flash('Database connection failed', 'danger')
        return redirect(url_for('index'))
    
    cursor = conn.cursor(dictionary=True)
    
    query = """
    SELECT * FROM trains 
    WHERE source_station LIKE %s AND destination_station LIKE %s 
    ORDER BY departure_time
    """
    cursor.execute(query, (f'%{source}%', f'%{destination}%'))
    trains = cursor.fetchall()
    
    # Calculate duration for each train
    for train in trains:
        if train['departure_time'] and train['arrival_time']:
            # Convert string times to datetime objects if needed
            if isinstance(train['departure_time'], str):
                dep_time = datetime.strptime(str(train['departure_time']), '%H:%M:%S')
                arr_time = datetime.strptime(str(train['arrival_time']), '%H:%M:%S')
            else:
                dep_time = train['departure_time']
                arr_time = train['arrival_time']
            
            # Calculate duration
            duration = arr_time - dep_time
            # Handle overnight journeys (negative duration)
            if duration.total_seconds() < 0:
                duration = timedelta(days=1) + duration
            
            # Convert to hours and minutes
            total_seconds = duration.total_seconds()
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            train['duration'] = f"{hours}h {minutes}m"
        else:
            train['duration'] = "N/A"

    cursor.close()
    conn.close()
    
    return render_template('search_results.html', trains=trains, date=journey_date, source=source, destination=destination)

@app.route('/book_ticket/<int:train_id>', methods=['GET', 'POST'])
def book_ticket(train_id):
    if 'user_id' not in session:
        flash('Please login to book tickets', 'warning')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if not conn:
        flash('Database connection failed', 'danger')
        return redirect(url_for('index'))
    
    cursor = conn.cursor(dictionary=True)
    
    # Get train details
    cursor.execute("SELECT * FROM trains WHERE id = %s", (train_id,))
    train = cursor.fetchone()
    
    if not train:
        flash('Train not found', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        journey_date = request.form['journey_date']
        passengers = []
        
        # Collect passenger details
        passenger_count = int(request.form['passenger_count'])
        
        if passenger_count > train['available_seats']:
            flash('Not enough seats available', 'danger')
            cursor.close()
            conn.close()
            return render_template('book_ticket.html', train=train)
        
        total_fare = train['fare'] * passenger_count
        
        for i in range(1, passenger_count + 1):
            passenger = {
                'name': request.form[f'passenger_name_{i}'],
                'age': request.form[f'passenger_age_{i}'],
                'gender': request.form[f'passenger_gender_{i}']
            }
            passengers.append(passenger)
        
        try:
            # Create booking
            cursor.execute(
                "INSERT INTO bookings (user_id, train_id, journey_date, passengers, total_fare) VALUES (%s, %s, %s, %s, %s)",
                (session['user_id'], train_id, journey_date, json.dumps(passengers), total_fare)
            )
            
            # Update available seats
            cursor.execute(
                "UPDATE trains SET available_seats = available_seats - %s WHERE id = %s",
                (passenger_count, train_id)
            )
            
            conn.commit()
            booking_id = cursor.lastrowid
            
            flash(f'Ticket booked successfully! Booking ID: {booking_id}', 'success')
            cursor.close()
            conn.close()
            return redirect(url_for('my_bookings'))
        except Exception as e:
            conn.rollback()
            flash(f'Booking failed: {str(e)}', 'danger')
            cursor.close()
            conn.close()
            return render_template('book_ticket.html', train=train)
    
    cursor.close()
    conn.close()
    return render_template('book_ticket.html', train=train)

@app.route("/my_bookings")
def my_bookings():
    if 'user_id' not in session:
        flash('Please login to view your bookings', 'warning')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if not conn:
        flash('Database connection failed', 'danger')
        return redirect(url_for('index'))
    
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT b.*, t.train_number, t.train_name, t.source_station, t.destination_station, t.departure_time, t.arrival_time
        FROM bookings b
        JOIN trains t ON b.train_id = t.id
        WHERE b.user_id = %s
        ORDER BY b.booking_date DESC
    """, (session['user_id'],))
    
    bookings = cursor.fetchall()
    
    # Parse passenger data from JSON
    for booking in bookings:
        try:
            booking['passengers'] = json.loads(booking['passengers'])
        except:
            booking['passengers'] = []
    
    cursor.close()
    conn.close()
    
    return render_template('my_bookings.html', bookings=bookings)

@app.route("/chat_support")
def chat_support():
    if 'user_id' not in session:
        flash('Please login to access chat support', 'warning')
        return redirect(url_for('login'))
    return render_template("chat_support.html")

@app.route('/chat_process', methods=['POST'])
def chat_process():
    if 'user_id' not in session:
        return jsonify({'error': 'Please login first'}), 401
    
    user_message = request.form['message']
    
    # Get database schema and sample data for context
    db_context = """
    Database Schema: trains
    - id: Primary key
    - train_number: String (e.g., '12301')
    - train_name: String (e.g., 'Rajdhani Express')
    - source_station: String (e.g., 'New Delhi')
    - destination_station: String (e.g., 'Mumbai')
    - departure_time: Time (e.g., '16:00:00')
    - arrival_time: Time (e.g., '08:00:00')
    - total_seats: Integer (e.g., 300)
    - available_seats: Integer (e.g., 250)
    - fare: Decimal (e.g., 2500.00)
    
    Current available trains include:
    """
    
    # Add actual train data to context
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT train_number, train_name, source_station, destination_station, departure_time, arrival_time, fare FROM trains")
            trains = cursor.fetchall()
            
            for train in trains:
                db_context += f"- {train['train_number']} {train['train_name']}: {train['source_station']} to {train['destination_station']} at {train['departure_time']}, Fare: ₹{train['fare']}\n"
            
            cursor.close()
        except Exception as e:
            print(f"Error fetching train data: {e}")
        finally:
            conn.close()
    
    # Create the prompt with strict instructions
    prompt = f"""
    You are a railway booking support assistant. You have access to the following train database information:
    
    {db_context}
    
    User Question: {user_message}
    
    IMPORTANT INSTRUCTIONS:
    1. Only provide information about trains, schedules, fares, and booking related queries
    2. If the question is not related to trains or railway booking, politely decline to answer
    3. Be helpful and friendly but stay strictly within the context of railway services
    4. If you don't have information about a specific train or route, say so honestly
    5. Do not make up or hallucinate information - only use what's provided in the context
    6. Keep responses concise and to the point
    7. If users ask about booking, guide them to use the booking system on the website
    """
    
    try:
        response = model.generate_content(prompt)
        return jsonify({'response': response.text})
    except Exception as e:
        return jsonify({'error': f'Sorry, I encountered an error: {str(e)}'}), 500

# Add this route to your app.py
@app.route('/download_ticket/<int:booking_id>')
def download_ticket(booking_id):
    if 'user_id' not in session:
        flash('Please login to download tickets', 'warning')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if not conn:
        flash('Database connection failed', 'danger')
        return redirect(url_for('my_bookings'))
    
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT b.*, t.train_number, t.train_name, t.source_station, t.destination_station, 
               t.departure_time, t.arrival_time, u.name as passenger_name, u.email
        FROM bookings b
        JOIN trains t ON b.train_id = t.id
        JOIN users u ON b.user_id = u.id
        WHERE b.id = %s AND b.user_id = %s
    """, (booking_id, session['user_id']))
    
    booking = cursor.fetchone()
    
    if not booking:
        cursor.close()
        conn.close()
        flash('Booking not found', 'danger')
        return redirect(url_for('my_bookings'))
    
    # Parse passenger data from JSON
    try:
        booking['passengers'] = json.loads(booking['passengers'])
    except:
        booking['passengers'] = []
    
    cursor.close()
    conn.close()
    
    # Create PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                           rightMargin=72, leftMargin=72,
                           topMargin=72, bottomMargin=72)
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Heading1'],
        fontSize=20,
        spaceAfter=30,
        alignment=1,  # Center aligned
        textColor=colors.HexColor('#1a237e')
    )
    
    elements.append(Paragraph("RAILWAY TICKET", title_style))
    elements.append(Spacer(1, 20))
    
    # Booking Info Table
    booking_data = [
        ['Booking ID:', str(booking['id'])],
        ['Booking Date:', booking['booking_date'].strftime('%d %b %Y, %I:%M %p')],
        ['Journey Date:', booking['journey_date'].strftime('%d %b %Y')],
        ['Train:', f"{booking['train_number']} - {booking['train_name']}"],
        ['Route:', f"{booking['source_station']} to {booking['destination_station']}"],
        ['Timing:', f"{booking['departure_time']} to {booking['arrival_time']}"],
        ['Total Fare:', f"₹{booking['total_fare']}"],
        ['Booked By:', f"{booking['passenger_name']} ({booking['email']})"]
    ]
    
    booking_table = Table(booking_data, colWidths=[2*inch, 3*inch])
    booking_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a237e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(booking_table)
    elements.append(Spacer(1, 30))
    
    # Passengers Table
    if booking['passengers']:
        elements.append(Paragraph("PASSENGER DETAILS", styles['Heading2']))
        elements.append(Spacer(1, 10))
        
        passenger_data = [['Name', 'Age', 'Gender']]
        for passenger in booking['passengers']:
            passenger_data.append([
                passenger['name'],
                str(passenger['age']),
                passenger['gender'].capitalize()
            ])
        
        passenger_table = Table(passenger_data, colWidths=[2.5*inch, 1*inch, 1.5*inch])
        passenger_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d47a1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#e3f2fd')),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(passenger_table)
    
    elements.append(Spacer(1, 30))
    
    # Terms and Conditions
    terms_style = ParagraphStyle(
        'Terms',
        parent=styles['BodyText'],
        fontSize=9,
        textColor=colors.grey
    )
    
    terms = """
    <b>Terms & Conditions:</b><br/>
    1. This is an electronic ticket. Please carry a valid photo ID proof.<br/>
    2. Boarding point: Please arrive at the station 30 minutes before departure.<br/>
    3. Ticket is non-transferable and valid only for the journey date.<br/>
    4. Cancellation charges apply as per railway rules.<br/>
    5. For any queries, contact support@railbook.com or call 1800-XXX-XXXX.
    """
    
    elements.append(Paragraph(terms, terms_style))
    elements.append(Spacer(1, 20))
    
    # Footer
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['BodyText'],
        fontSize=10,
        alignment=1,
        textColor=colors.HexColor('#666666')
    )
    
    footer = f"""
    Generated on {datetime.now().strftime('%d %b %Y, %I:%M %p')} | RailBook Ticket Booking System
    """
    
    elements.append(Paragraph(footer, footer_style))
    
    # Build PDF
    doc.build(elements)
    
    buffer.seek(0)
    
    filename = f"ticket_{booking['train_number']}_{booking['journey_date']}.pdf"
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf'
    )

@app.route("/all_trains")
def all_trains():
    if 'user_id' not in session:
        flash('Please login to view trains', 'warning')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    trains = []
    
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM trains ORDER BY train_name")
            trains = cursor.fetchall()
            
            # Calculate duration for each train
            for train in trains:
                if train['departure_time'] and train['arrival_time']:
                    # Convert string times to datetime objects if needed
                    if isinstance(train['departure_time'], str):
                        dep_time = datetime.strptime(str(train['departure_time']), '%H:%M:%S')
                        arr_time = datetime.strptime(str(train['arrival_time']), '%H:%M:%S')
                    else:
                        dep_time = train['departure_time']
                        arr_time = train['arrival_time']
                    
                    # Calculate duration
                    duration = arr_time - dep_time
                    # Handle overnight journeys (negative duration)
                    if duration.total_seconds() < 0:
                        duration = timedelta(days=1) + duration
                    
                    # Convert to hours and minutes
                    total_seconds = duration.total_seconds()
                    hours = int(total_seconds // 3600)
                    minutes = int((total_seconds % 3600) // 60)
                    train['duration'] = f"{hours}h {minutes}m"
                else:
                    train['duration'] = "N/A"
            
            cursor.close()
        except Exception as e:
            print(f"Error fetching trains: {e}")
        finally:
            conn.close()
    
    return render_template('all_trains.html', trains=trains)


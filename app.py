# app.py

import os
import uuid
from flask import Flask, render_template, redirect, url_for, flash, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user, login_user, logout_user, login_required
from flask_bcrypt import Bcrypt
from datetime import datetime, date, time, timedelta
import cloudinary
import cloudinary.uploader
import cloudinary.api

# --- CONFIGURAÇÃO DA APLICAÇÃO ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'uma-chave-secreta-muito-segura-e-diferente-para-testes'
db_url = os.environ.get('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///app.db'

# --- INICIALIZAÇÃO DAS EXTENSÕES ---
from models import db, User, Patient, Appointment, ElectronicRecord, Assessment, UploadedFile
db.init_app(app)
migrate = Migrate(app, db)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Por favor, faça o login para acessar esta página.'
login_manager.login_message_category = 'info'

# --- CONFIGURAÇÃO DO CLOUDINARY ---
cloudinary.config(
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key = os.environ.get('CLOUDINARY_API_KEY'),
    api_secret = os.environ.get('CLOUDINARY_API_SECRET'),
    secure = True
)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.context_processor
def inject_global_variables():
    """Injeta variáveis globais em todos os templates."""
    return {
        'current_year': datetime.utcnow().year,
        'today': date.today()
    }

# --- ROTAS DE AUTENTICAÇÃO ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    from forms import RegistrationForm
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(name=form.name.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Sua conta foi criada com sucesso! Faça o login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Registrar', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    from forms import LoginForm
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Login sem sucesso. Verifique seu email e senha.', 'danger')
    return render_template('login.html', title='Login', form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

# --- ROTAS PRINCIPAIS E DE VISUALIZAÇÃO ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
@login_required
def dashboard():
    hoje = date.today()
    start_of_day = datetime.combine(hoje, time.min)
    end_of_day = datetime.combine(hoje, time.max)
    
    appointments_today = Appointment.query.filter(
        Appointment.user_id == current_user.id,
        Appointment.start_time.between(start_of_day, end_of_day)
    ).order_by(Appointment.start_time).all()

    total_patients = Patient.query.filter_by(user_id=current_user.id).count()
    total_appointments_month = Appointment.query.filter(
        Appointment.user_id == current_user.id,
        db.extract('month', Appointment.start_time) == hoje.month,
        db.extract('year', Appointment.start_time) == hoje.year
    ).count()

    return render_template('dashboard.html', appointments_today=appointments_today, 
                           total_patients=total_patients, total_appointments_month=total_appointments_month)

@app.route('/agenda')
@login_required
def agenda():
    return render_template('agenda_grid.html')

# --- ROTAS PARA PACIENTES ---
@app.route('/patients')
@login_required
def list_patients():
    page = request.args.get('page', 1, type=int)
    patients = Patient.query.filter_by(user_id=current_user.id).order_by(Patient.full_name).paginate(page=page, per_page=10)
    return render_template('list_patients.html', patients=patients)

@app.route('/patient/add', methods=['GET', 'POST'])
@login_required
def add_patient():
    from forms import PatientForm
    form = PatientForm()
    if form.validate_on_submit():
        new_patient = Patient(
            full_name=form.full_name.data,
            date_of_birth=form.date_of_birth.data,
            phone=form.phone.data,
            professional=current_user
        )
        db.session.add(new_patient)
        db.session.commit()
        flash('Paciente cadastrado com sucesso!', 'success')
        return redirect(url_for('list_patients'))
    return render_template('add_edit_patient.html', form=form, title="Adicionar Paciente")

@app.route('/patient/<int:patient_id>')
@login_required
def patient_detail(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    if patient.user_id != current_user.id:
        flash('Acesso não autorizado.', 'danger')
        return redirect(url_for('list_patients'))
    
    records = patient.records.order_by(ElectronicRecord.record_date.desc()).all()
    assessments = patient.assessments.order_by(Assessment.created_at.desc()).all()
    return render_template('patient_detail.html', patient=patient, records=records, assessments=assessments)

# --- ROTAS DE PRONTUÁRIO E AVALIAÇÃO ---
@app.route('/patient/<int:patient_id>/add_record', methods=['GET', 'POST'])
@login_required
def add_record(patient_id):
    from forms import ElectronicRecordForm
    patient = Patient.query.get_or_404(patient_id)
    if patient.user_id != current_user.id:
        return redirect(url_for('list_patients'))
        
    form = ElectronicRecordForm()
    if form.validate_on_submit():
        record = ElectronicRecord(
            record_date=datetime.utcnow(),
            medical_diagnosis=form.medical_diagnosis.data,
            subjective_notes=form.subjective_notes.data,
            objective_notes=form.objective_notes.data,
            assessment=form.assessment.data,
            plan=form.plan.data,
            patient_id=patient.id
        )
        db.session.add(record)
        db.session.commit()
        flash('Registro adicionado ao prontuário com sucesso!', 'success')
        return redirect(url_for('patient_detail', patient_id=patient.id))
    return render_template('add_record.html', form=form, patient=patient, title="Adicionar ao Prontuário")

@app.route('/patient/<int:patient_id>/add_assessment', methods=['GET', 'POST'])
@login_required
def add_assessment(patient_id):
    from forms import AssessmentForm
    patient = Patient.query.get_or_404(patient_id)
    if patient.user_id != current_user.id:
        return redirect(url_for('list_patients'))

    form = AssessmentForm()
    if form.validate_on_submit():
        assessment = Assessment(
            patient_id=patient.id,
            main_complaint=form.main_complaint.data,
            history_of_present_illness=form.history_of_present_illness.data,
            past_medical_history=form.past_medical_history.data,
            medications=form.medications.data,
            social_history=form.social_history.data,
            inspection_notes=form.inspection_notes.data,
            palpation_notes=form.palpation_notes.data,
            mobility_assessment=form.mobility_assessment.data,
            strength_assessment=form.strength_assessment.data,
            neuro_assessment=form.neuro_assessment.data,
            functional_assessment=form.functional_assessment.data,
            diagnosis=form.diagnosis.data,
            goals=form.goals.data,
            treatment_plan=form.treatment_plan.data
        )
        db.session.add(assessment)
        db.session.commit()

        files = request.files.getlist(form.files.name)
        for file in files:
            if file:
                upload_result = cloudinary.uploader.upload(file)
                new_file = UploadedFile(
                    public_id=upload_result['public_id'],
                    secure_url=upload_result['secure_url'],
                    resource_type=upload_result['resource_type'],
                    assessment_id=assessment.id
                )
                db.session.add(new_file)

        db.session.commit()
        flash('Nova avaliação salva com sucesso!', 'success')
        return redirect(url_for('patient_detail', patient_id=patient.id))
        
    return render_template('add_assessment.html', title='Nova Avaliação', form=form, patient=patient)

@app.route('/assessment/<int:assessment_id>')
@login_required
def view_assessment(assessment_id):
    assessment = Assessment.query.get_or_404(assessment_id)
    if assessment.patient.user_id != current_user.id:
        flash('Acesso não autorizado.', 'danger')
        return redirect(url_for('list_patients'))
    return render_template('view_assessment.html', title='Detalhes da Avaliação', assessment=assessment)

# --- ROTAS PARA AGENDAMENTOS ---
@app.route('/appointment/schedule', methods=['GET', 'POST'])
@login_required
def schedule_appointment():
    from forms import AppointmentForm
    form = AppointmentForm()
    form.patient_id.choices = [(p.id, p.full_name) for p in Patient.query.filter_by(user_id=current_user.id).all()]
    
    if form.validate_on_submit():
        start_datetime = datetime.combine(form.date.data, form.time.data)
        
        if form.is_recurring.data:
            recurrence_id = str(uuid.uuid4())
            for i in range(form.frequency.data):
                recurrent_start_time = start_datetime + timedelta(weeks=i)
                appointment = Appointment(
                    start_time=recurrent_start_time,
                    location=form.location.data,
                    notes=form.notes.data,
                    is_recurring=True,
                    recurrence_id=recurrence_id,
                    professional=current_user,
                    patient_id=form.patient_id.data
                )
                db.session.add(appointment)
            flash(f'{form.frequency.data} sessões recorrentes agendadas com sucesso!', 'success')
        else:
            appointment = Appointment(
                start_time=start_datetime,
                location=form.location.data,
                notes=form.notes.data,
                professional=current_user,
                patient_id=form.patient_id.data
            )
            db.session.add(appointment)
            flash('Agendamento realizado com sucesso!', 'success')
        
        db.session.commit()
        return redirect(url_for('agenda'))
    
    return render_template('add_edit_appointment.html', form=form, title="Novo Agendamento")

@app.route('/appointment/<int:appointment_id>/update_status', methods=['POST'])
@login_required
def update_appointment_status(appointment_id):
    from forms import UpdateAppointmentStatusForm
    appointment = Appointment.query.get_or_404(appointment_id)
    if appointment.user_id != current_user.id:
        return jsonify({'status': 'error', 'message': 'Não autorizado'}), 403
    
    form = UpdateAppointmentStatusForm()
    if form.validate_on_submit():
        appointment.status = form.status.data
        db.session.commit()
        flash('Status do agendamento atualizado.', 'success')
    else:
        flash('Ocorreu um erro ao atualizar o status.', 'danger')
        
    return redirect(request.referrer or url_for('agenda'))
    
# --- ROTA DE RELATÓRIOS ---
@app.route('/reports')
@login_required
def reports():
    hoje = date.today()
    
    start_of_month = hoje.replace(day=1)
    appointments_this_month = Appointment.query.filter(
        Appointment.user_id == current_user.id,
        Appointment.start_time >= start_of_month
    ).all()
    
    status_counts = {
        'Concluído': len([a for a in appointments_this_month if a.status == 'Concluído']),
        'Agendado': len([a for a in appointments_this_month if a.status == 'Agendado']),
        'Cancelado': len([a for a in appointments_this_month if a.status == 'Cancelado'])
    }
    
    new_patients_data = {}
    for i in range(6):
        target_date = hoje.replace(day=1) - timedelta(days=i * 30)
        target_month = target_date.month
        target_year = target_date.year
        month_key = target_date.strftime("%b/%Y")
        
        count = Patient.query.filter(
            Patient.user_id == current_user.id,
            db.extract('month', Patient.created_at) == target_month,
            db.extract('year', Patient.created_at) == target_year
        ).count()
        new_patients_data[month_key] = count
        
    return render_template('reports.html', status_counts=status_counts, new_patients_data=new_patients_data)

# --- API ENDPOINT PARA O FULLCALENDAR ---
@app.route('/api/appointments')
@login_required
def api_appointments():
    appointments = Appointment.query.filter_by(user_id=current_user.id).all()
    
    status_colors = {
        'Concluído': '#28a745',
        'Agendado': '#0dcaf0',
        'Cancelado': '#dc3545'
    }
    
    eventos = []
    for appt in appointments:
        eventos.append({
            'id': appt.id,
            'title': appt.patient.full_name,
            'start': appt.start_time.isoformat(),
            'color': status_colors.get(appt.status, '#6c757d'),
            'borderColor': status_colors.get(appt.status, '#6c757d'),
            'extendedProps': {
                'location': appt.location,
                'status': appt.status
            }
        })
    return jsonify(eventos)

# --- COMANDO PARA INICIALIZAR O BANCO DE DADOS ---
@app.cli.command("init-db")
def init_db_command():
    db.create_all()
    print("Banco de dados inicializado e tabelas criadas.")

if __name__ == '__main__':
    app.run(debug=True)
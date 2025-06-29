# app.py (COMPLETO E ATUALIZADO)

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
from sqlalchemy import func, extract

# --- CONFIGURAÇÃO DA APLICAÇÃO ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'uma-chave-secreta-muito-segura-e-diferente-para-testes'
db_url = os.environ.get('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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
    return {
        'current_year': datetime.utcnow().year,
        'today': date.today()
    }

# --- ROTAS DE AUTENTICAÇÃO ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
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
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
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
    hoje = datetime.utcnow()
    
    proximos_agendamentos = Appointment.query.filter(
        Appointment.user_id == current_user.id,
        Appointment.start_time >= hoje
    ).order_by(Appointment.start_time.asc()).limit(5).all()

    ultimos_pacientes = Patient.query.filter_by(
        user_id=current_user.id
    ).order_by(Patient.created_at.desc()).limit(5).all()

    aniversariantes_do_mes = Patient.query.filter(
        Patient.user_id == current_user.id,
        extract('month', Patient.date_of_birth) == hoje.month
    ).order_by(extract('day', Patient.date_of_birth).asc()).all()

    return render_template(
        'dashboard.html',
        proximos_agendamentos=proximos_agendamentos,
        ultimos_pacientes=ultimos_pacientes,
        aniversariantes_do_mes=aniversariantes_do_mes
    )

@app.route('/agenda')
@login_required
def agenda():
    return render_template('agenda_grid.html')

# --- ROTAS PARA PACIENTES ---
@app.route('/patients')
@login_required
def list_patients():
    """Exibe um painel completo com todos os pacientes do profissional."""
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('q', '')

    patients_query = Patient.query.filter_by(user_id=current_user.id)

    if search_query:
        patients_query = patients_query.filter(Patient.full_name.ilike(f'%{search_query}%'))

    patients_pagination = patients_query.order_by(Patient.full_name).paginate(page=page, per_page=10)
    
    patients_enriched = []
    for patient in patients_pagination.items:
        appointment_count = patient.appointments.count()
        latest_record = patient.records.order_by(ElectronicRecord.record_date.desc()).first()
        latest_diagnosis = latest_record.medical_diagnosis if (latest_record and latest_record.medical_diagnosis) else "N/A"

        patients_enriched.append({
            'data': patient,
            'appointment_count': appointment_count,
            'latest_diagnosis': latest_diagnosis
        })

    return render_template(
        'list_patients.html',
        patients_pagination=patients_pagination,
        patients_enriched=patients_enriched,
        search_query=search_query,
        title="Painel de Pacientes"
    )

@app.route('/patient/add', methods=['GET', 'POST'])
@login_required
def add_patient():
    from forms import PatientForm
    form = PatientForm()
    if form.validate_on_submit():
        new_patient = Patient(full_name=form.full_name.data, date_of_birth=form.date_of_birth.data, gender=form.gender.data, phone=form.phone.data, specialty=form.specialty.data, professional=current_user)
        db.session.add(new_patient)
        db.session.commit()
        flash('Paciente cadastrado com sucesso!', 'success')
        return redirect(url_for('list_patients'))
    return render_template('add_edit_patient.html', form=form, title="Adicionar Paciente")

@app.route('/patient/<int:patient_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    if patient.user_id != current_user.id:
        flash('Acesso não autorizado.', 'danger')
        return redirect(url_for('list_patients'))
    from forms import PatientForm
    form = PatientForm(obj=patient)
    if form.validate_on_submit():
        patient.full_name = form.full_name.data
        patient.date_of_birth = form.date_of_birth.data
        patient.gender = form.gender.data
        patient.phone = form.phone.data
        patient.specialty = form.specialty.data
        db.session.commit()
        flash('Dados do paciente atualizados com sucesso!', 'success')
        return redirect(url_for('list_patients'))
    return render_template('add_edit_patient.html', form=form, title="Editar Paciente")

@app.route('/patient/<int:patient_id>')
@login_required
def patient_detail(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    if patient.user_id != current_user.id: return redirect(url_for('list_patients'))
    records = patient.records.order_by(ElectronicRecord.record_date.desc()).all()
    assessments = patient.assessments.order_by(Assessment.created_at.desc()).all()
    return render_template('patient_detail.html', patient=patient, records=records, assessments=assessments)

# --- ROTAS DE PRONTUÁRIO E AVALIAÇÃO ---
@app.route('/patient/<int:patient_id>/add_record', methods=['GET', 'POST'])
@login_required
def add_record(patient_id):
    from forms import ElectronicRecordForm
    patient = Patient.query.get_or_404(patient_id)
    if patient.user_id != current_user.id: return redirect(url_for('list_patients'))
    form = ElectronicRecordForm()
    if form.validate_on_submit():
        record = ElectronicRecord(record_date=datetime.utcnow(), medical_diagnosis=form.medical_diagnosis.data, subjective_notes=form.subjective_notes.data, objective_notes=form.objective_notes.data, assessment=form.assessment.data, plan=form.plan.data, patient_id=patient.id)
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
    if patient.user_id != current_user.id: return redirect(url_for('list_patients'))
    form = AssessmentForm()
    if form.validate_on_submit():
        assessment = Assessment(patient_id=patient.id, main_complaint=form.main_complaint.data, history_of_present_illness=form.history_of_present_illness.data, past_medical_history=form.past_medical_history.data, medications=form.medications.data, social_history=form.social_history.data, inspection_notes=form.inspection_notes.data, palpation_notes=form.palpation_notes.data, mobility_assessment=form.mobility_assessment.data, strength_assessment=form.strength_assessment.data, neuro_assessment=form.neuro_assessment.data, functional_assessment=form.functional_assessment.data, diagnosis=form.diagnosis.data, goals=form.goals.data, treatment_plan=form.treatment_plan.data)
        db.session.add(assessment)
        db.session.commit()
        files = request.files.getlist(form.files.name)
        for file in files:
            if file:
                upload_result = cloudinary.uploader.upload(file)
                new_file = UploadedFile(public_id=upload_result['public_id'], secure_url=upload_result['secure_url'], resource_type=upload_result['resource_type'], assessment_id=assessment.id)
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

# --- ROTAS PARA AGENDAMENTOS E APIS ---
@app.route('/appointment/schedule', methods=['GET', 'POST'])
@login_required
def schedule_appointment():
    from forms import AppointmentForm
    form = AppointmentForm()
    form.patient_id.choices = [(p.id, p.full_name) for p in Patient.query.filter_by(user_id=current_user.id).order_by(Patient.full_name).all()]
    if form.validate_on_submit():
        return redirect(url_for('agenda'))
    return render_template('add_edit_appointment.html', form=form, title="Novo Agendamento")

@app.route('/api/appointment/create_from_agenda', methods=['POST'])
@login_required
def create_from_agenda():
    data = request.get_json()
    try:
        patient_id = data['patient_id']
        start_datetime_str = data['start_datetime']
        location = data.get('location', 'Clínica')
        price = data.get('price')
        notes = data.get('notes', '')
        is_recurring = data.get('is_recurring', False)
        start_datetime = datetime.fromisoformat(start_datetime_str.replace('Z', '+00:00'))
        price_float = float(price) if price else None
        if not is_recurring:
            appointment = Appointment(start_time=start_datetime, location=location, notes=notes, price=price_float, payment_status='Pendente', professional=current_user, patient_id=patient_id)
            db.session.add(appointment)
        else:
            weeks_to_repeat = int(data.get('weeks_to_repeat', 1))
            weekdays_str = data.get('weekdays', [])
            if not weekdays_str: return jsonify({'status': 'error', 'message': 'Selecione os dias da semana.'}), 400
            weekdays = [int(d) for d in weekdays_str]
            recurrence_id = str(uuid.uuid4())
            start_date_of_series = start_datetime.date()
            for i in range(weeks_to_repeat):
                for weekday in weekdays:
                    current_week_start_date = start_date_of_series + timedelta(weeks=i)
                    days_ahead = weekday - current_week_start_date.weekday()
                    target_date = current_week_start_date + timedelta(days=days_ahead)
                    recurrent_start_time = datetime.combine(target_date, start_datetime.time())
                    if recurrent_start_time.date() >= start_date_of_series:
                        appointment = Appointment(start_time=recurrent_start_time, location=location, notes=notes, is_recurring=True, recurrence_id=recurrence_id, price=price_float, payment_status='Pendente', professional=current_user, patient_id=patient_id)
                        db.session.add(appointment)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Agendamento(s) criado(s) com sucesso!'})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Erro ao criar agendamento: {e}")
        return jsonify({'status': 'error', 'message': 'Ocorreu um erro interno.'}), 500

@app.route('/api/appointment/<int:appointment_id>/update_payment', methods=['POST'])
@login_required
def update_payment_status(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    if appointment.user_id != current_user.id: return jsonify({'status': 'error', 'message': 'Não autorizado'}), 403
    data = request.get_json()
    new_status = data.get('payment_status')
    if new_status not in ['Pendente', 'Pago']: return jsonify({'status': 'error', 'message': 'Status de pagamento inválido.'}), 400
    appointment.payment_status = new_status
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'Status do pagamento atualizado.'})

@app.route('/api/appointments')
@login_required
def api_appointments():
    appointments = Appointment.query.filter_by(user_id=current_user.id).all()
    eventos = []
    for appt in appointments:
        eventos.append({'id': appt.id, 'title': appt.patient.full_name, 'start': appt.start_time.isoformat(), 'extendedProps': {'location': appt.location, 'status': appt.status, 'notes': appt.notes, 'price': appt.price, 'payment_status': appt.payment_status, 'patient_id': appt.patient_id}})
    return jsonify(eventos)

@app.route('/api/patients')
@login_required
def api_patients():
    patients = Patient.query.filter_by(user_id=current_user.id).order_by(Patient.full_name).all()
    return jsonify([{'id': p.id, 'name': p.full_name} for p in patients])

# --- ROTA DE RELATÓRIOS ---
@app.route('/reports')
@login_required
def reports():
    hoje = date.today()
    start_of_month = hoje.replace(day=1)
    
    appointments_this_month = Appointment.query.filter(Appointment.user_id == current_user.id, Appointment.start_time >= start_of_month).all()
    status_counts = {'Concluído': 0, 'Agendado': 0, 'Cancelado': 0}
    for appt in appointments_this_month:
        if appt.status in status_counts: status_counts[appt.status] += 1
    
    new_patients_data = {}
    for i in range(6):
        target_date = hoje.replace(day=1) - timedelta(days=i * 30)
        month_key = target_date.strftime("%b/%Y")
        count = db.session.query(func.count(Patient.id)).filter(Patient.user_id == current_user.id, func.to_char(Patient.created_at, 'YYYY-MM') == target_date.strftime('%Y-%m')).scalar()
        new_patients_data[month_key] = count
    
    total_recebido_query = db.session.query(func.sum(Appointment.price)).filter(Appointment.user_id == current_user.id, Appointment.payment_status == 'Pago', Appointment.start_time >= start_of_month).scalar()
    total_recebido = total_recebido_query or 0.0
    total_pendente_query = db.session.query(func.sum(Appointment.price)).filter(Appointment.user_id == current_user.id, Appointment.payment_status == 'Pendente', Appointment.start_time >= start_of_month).scalar()
    total_pendente = total_pendente_query or 0.0

    return render_template('reports.html', status_counts=status_counts, new_patients_data=new_patients_data, total_recebido=total_recebido, total_pendente=total_pendente)


# --- COMANDO PARA INICIALIZAR O BANCO DE DADOS ---
@app.cli.command("init-db")
def init_db_command():
    db.create_all()
    print("Banco de dados inicializado e tabelas criadas.")

if __name__ == '__main__':
    app.run(debug=True)
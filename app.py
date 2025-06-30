# app.py (COMPLETO E ATUALIZADO)

import os
import uuid
from flask import Flask, render_template, redirect, url_for, flash, jsonify, request, abort
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user, login_user, logout_user, login_required
from flask_bcrypt import Bcrypt
from datetime import datetime, date, time, timedelta
import cloudinary
import cloudinary.uploader
import cloudinary.api
from sqlalchemy import func, extract
from collections import defaultdict

# --- CONFIGURAÇÃO DA APLICAÇÃO ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'uma-chave-secreta-muito-segura-e-diferente-para-testes'
db_url = os.environ.get('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- INICIALIZAÇÃO DAS EXTENSÕES ---
from models import db, User, Patient, Appointment, ElectronicRecord, Assessment, UploadedFile, Clinic
db.init_app(app)
migrate = Migrate(app, db)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Por favor, faça o login para acessar esta página.'
login_manager.login_message_category = 'info'

# --- CONFIGURAÇÃO DO CLOUDINARY ---
cloudinary.config(cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'), api_key=os.environ.get('CLOUDINARY_API_KEY'), api_secret=os.environ.get('CLOUDINARY_API_SECRET'), secure=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.context_processor
def inject_global_variables():
    return {'current_year': datetime.utcnow().year, 'today': date.today()}

# --- ROTAS DE AUTENTICAÇÃO E GESTÃO (sem alterações) ---
# ... (todas as rotas desde /register até /assessment/<id> permanecem iguais)
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    from forms import RegistrationForm
    form = RegistrationForm()
    if form.validate_on_submit():
        new_clinic = Clinic(name=f"Clínica de {form.name.data}")
        db.session.add(new_clinic)
        db.session.commit()
        user = User(name=form.name.data, email=form.email.data, clinic_id=new_clinic.id)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Sua conta e sua clínica foram criadas com sucesso! Faça o login.', 'success')
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
@login_required
def dashboard():
    hoje = datetime.utcnow()
    proximos_agendamentos = Appointment.query.join(User).filter(User.clinic_id == current_user.clinic_id, Appointment.start_time >= hoje).order_by(Appointment.start_time.asc()).limit(5).all()
    ultimos_pacientes = Patient.query.filter_by(clinic_id=current_user.clinic_id).order_by(Patient.created_at.desc()).limit(5).all()
    aniversariantes_do_mes = Patient.query.filter(Patient.clinic_id == current_user.clinic_id, extract('month', Patient.date_of_birth) == hoje.month).order_by(extract('day', Patient.date_of_birth).asc()).all()
    return render_template('dashboard.html', proximos_agendamentos=proximos_agendamentos, ultimos_pacientes=ultimos_pacientes, aniversariantes_do_mes=aniversariantes_do_mes)

@app.route('/agenda')
@login_required
def agenda():
    return render_template('agenda_grid.html')

@app.route('/patients')
@login_required
def list_patients():
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('q', '')
    patients_query = Patient.query.filter_by(clinic_id=current_user.clinic_id)
    if search_query:
        patients_query = patients_query.filter(Patient.full_name.ilike(f'%{search_query}%'))
    patients_pagination = patients_query.order_by(Patient.full_name).paginate(page=page, per_page=10)
    patients_enriched = []
    for patient in patients_pagination.items:
        appointment_count = patient.appointments.count()
        latest_record = patient.records.order_by(ElectronicRecord.record_date.desc()).first()
        latest_diagnosis = latest_record.medical_diagnosis if (latest_record and latest_record.medical_diagnosis) else "N/A"
        patients_enriched.append({'data': patient, 'appointment_count': appointment_count, 'latest_diagnosis': latest_diagnosis})
    return render_template('list_patients.html', patients_pagination=patients_pagination, patients_enriched=patients_enriched, search_query=search_query, title="Painel de Pacientes")

@app.route('/patient/add', methods=['GET', 'POST'])
@login_required
def add_patient():
    from forms import PatientForm
    form = PatientForm()
    if form.validate_on_submit():
        new_patient = Patient(full_name=form.full_name.data, date_of_birth=form.date_of_birth.data, gender=form.gender.data, phone=form.phone.data, specialty=form.specialty.data, professional=current_user, clinic_id=current_user.clinic_id)
        db.session.add(new_patient)
        db.session.commit()
        flash('Paciente cadastrado com sucesso!', 'success')
        return redirect(url_for('list_patients'))
    return render_template('add_edit_patient.html', form=form, title="Adicionar Paciente")

@app.route('/patient/<int:patient_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    if patient.clinic_id != current_user.clinic_id: abort(403)
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

@app.route('/patient/<int:patient_id>/delete', methods=['POST'])
@login_required
def delete_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    if patient.clinic_id != current_user.clinic_id: abort(403)
    db.session.delete(patient)
    db.session.commit()
    flash(f'O paciente {patient.full_name} e todos os seus registos foram apagados com sucesso.', 'success')
    return redirect(url_for('list_patients'))

@app.route('/patient/<int:patient_id>')
@login_required
def patient_detail(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    if patient.clinic_id != current_user.clinic_id: abort(403)
    records = patient.records.order_by(ElectronicRecord.record_date.desc()).all()
    assessments = patient.assessments.order_by(Assessment.created_at.desc()).all()
    return render_template('patient_detail.html', patient=patient, records=records, assessments=assessments)

@app.route('/patient/<int:patient_id>/add_record', methods=['GET', 'POST'])
@login_required
def add_record(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    if patient.clinic_id != current_user.clinic_id: abort(403)
    from forms import ElectronicRecordForm
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
    patient = Patient.query.get_or_404(patient_id)
    if patient.clinic_id != current_user.clinic_id: abort(403)
    from forms import AssessmentForm
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
    if assessment.patient.clinic_id != current_user.clinic_id: abort(403)
    return render_template('view_assessment.html', title='Detalhes da Avaliação', assessment=assessment)

# --- APIS E ROTAS DE AGENDAMENTO ---
# ... (a maioria das APIs permanece igual)

# ROTA ADICIONADA: PARA SALVAR AS ALTERAÇÕES DO AGENDAMENTO
@app.route('/api/appointment/<int:appointment_id>/update', methods=['POST'])
@login_required
def update_appointment(appointment_id):
    appointment = db.session.query(Appointment).join(User).filter(
        Appointment.id == appointment_id,
        User.clinic_id == current_user.clinic_id
    ).first_or_404()
    
    data = request.get_json()
    try:
        if 'start_time' in data and data['start_time']:
            appointment.start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
        if 'location' in data:
            appointment.location = data['location']
        if 'session_price' in data:
            appointment.session_price = float(data['session_price'] or 0.0)
        if 'notes' in data:
            appointment.notes = data['notes']
            
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Agendamento atualizado com sucesso.'})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Erro ao atualizar agendamento: {e}")
        return jsonify({'status': 'error', 'message': f'Ocorreu um erro interno: {e}'}), 500


# ... (o resto das suas APIs e rotas, sem alterações)
@app.route('/api/appointment/create_from_agenda', methods=['POST'])
@login_required
def create_from_agenda():
    data = request.get_json()
    try:
        patient_id = data['patient_id']
        patient = Patient.query.filter_by(id=patient_id, clinic_id=current_user.clinic_id).first_or_404()
        start_datetime_str = data['start_datetime']
        location = data.get('location', 'Clínica')
        session_price = data.get('session_price')
        notes = data.get('notes', '')
        is_recurring = data.get('is_recurring', False)
        start_datetime = datetime.fromisoformat(start_datetime_str.replace('Z', '+00:00'))
        price_float = float(session_price) if session_price else None
        def create_single_appointment(appt_time, rec_id=None):
            new_appt = Appointment(start_time=appt_time, location=location, notes=notes, session_price=price_float, amount_paid=0.0, is_recurring=is_recurring, recurrence_id=rec_id, professional=current_user, patient_id=patient.id)
            db.session.add(new_appt)
        if not is_recurring:
            create_single_appointment(start_datetime)
        else:
            weeks_to_repeat = int(data.get('weeks_to_repeat', 1))
            weekdays = [int(d) for d in data.get('weekdays', [])]
            if not weekdays: return jsonify({'status': 'error', 'message': 'Selecione os dias da semana.'}), 400
            recurrence_id = str(uuid.uuid4())
            start_date_of_series = start_datetime.date()
            for i in range(weeks_to_repeat):
                for weekday in weekdays:
                    current_week_start_date = start_date_of_series + timedelta(weeks=i)
                    days_ahead = weekday - current_week_start_date.weekday()
                    target_date = current_week_start_date + timedelta(days=days_ahead)
                    if target_date >= start_date_of_series:
                        recurrent_start_time = datetime.combine(target_date, start_datetime.time())
                        create_single_appointment(recurrent_start_time, rec_id=recurrence_id)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Agendamento(s) criado(s) com sucesso!'})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Erro ao criar agendamento: {e}")
        return jsonify({'status': 'error', 'message': f'Ocorreu um erro interno: {e}'}), 500

@app.route('/api/appointment/<int:appointment_id>/update_financials', methods=['POST'])
@login_required
def update_financials(appointment_id):
    appointment = db.session.query(Appointment).join(User).filter(Appointment.id == appointment_id, User.clinic_id == current_user.clinic_id).first_or_404()
    data = request.get_json()
    try:
        appointment.session_price = float(data.get('session_price', 0.0) or 0.0)
        appointment.amount_paid = float(data.get('amount_paid', 0.0) or 0.0)
        appointment.payment_notes = data.get('payment_notes', '')
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Dados financeiros atualizados.'})
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'message': 'Valores inválidos. Use apenas números.'}), 400

@app.route('/api/appointment/<int:appointment_id>/<action>', methods=['POST'])
@login_required
def handle_appointment_action(appointment_id, action):
    appointment = db.session.query(Appointment).join(User).filter(Appointment.id == appointment_id, User.clinic_id == current_user.clinic_id).first_or_404()
    if action == 'complete':
        appointment.status = 'Concluído'
        message = 'Agendamento marcado como concluído.'
    elif action == 'cancel':
        appointment.status = 'Cancelado'
        message = 'Agendamento cancelado com sucesso.'
    elif action == 'delete':
        db.session.delete(appointment)
        message = 'Agendamento apagado permanentemente.'
    else:
        return jsonify({'status': 'error', 'message': 'Ação inválida.'}), 400
    db.session.commit()
    return jsonify({'status': 'success', 'message': message})

@app.route('/api/patient/<int:patient_id>/financial_balance')
@login_required
def financial_balance(patient_id):
    patient = Patient.query.filter_by(id=patient_id, clinic_id=current_user.clinic_id).first_or_404()
    total_due_query = db.session.query(func.sum(Appointment.session_price)).filter_by(patient_id=patient_id).scalar()
    total_paid_query = db.session.query(func.sum(Appointment.amount_paid)).filter_by(patient_id=patient_id).scalar()
    total_due = total_due_query or 0.0
    total_paid = total_paid_query or 0.0
    balance = total_paid - total_due
    return jsonify({'total_due': total_due, 'total_paid': total_paid, 'balance': balance})

@app.route('/api/appointments')
@login_required
def api_appointments():
    appointments = db.session.query(Appointment).join(User).filter(User.clinic_id == current_user.clinic_id).all()
    status_colors = {'Concluído': '#198754', 'Agendado': '#0dcaf0', 'Cancelado': '#6c757d'}
    eventos = []
    for appt in appointments:
        eventos.append({'id': appt.id, 'title': appt.patient.full_name, 'start': appt.start_time.isoformat(), 'color': status_colors.get(appt.status, '#6c757d'), 'borderColor': status_colors.get(appt.status, '#6c757d'), 'extendedProps': {'location': appt.location, 'status': appt.status, 'notes': appt.notes, 'session_price': appt.session_price, 'amount_paid': appt.amount_paid, 'payment_notes': appt.payment_notes, 'patient_id': appt.patient_id}})
    return jsonify(eventos)

@app.route('/api/patients')
@login_required
def api_patients():
    patients = Patient.query.filter_by(clinic_id=current_user.clinic_id).order_by(Patient.full_name).all()
    return jsonify([{'id': p.id, 'name': p.full_name} for p in patients])

@app.route('/reports')
@login_required
def reports():
    hoje = date.today()
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    if start_date_str and end_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    else:
        start_date = hoje.replace(day=1)
        next_month = start_date.replace(day=28) + timedelta(days=4)
        end_date = next_month - timedelta(days=next_month.day)
    start_datetime = datetime.combine(start_date, time.min)
    end_datetime = datetime.combine(end_date, time.max)
    financial_appointments = db.session.query(Appointment).join(User).filter(User.clinic_id == current_user.clinic_id, Appointment.start_time.between(start_datetime, end_datetime)).order_by(Appointment.start_time.desc()).all()
    total_cobrado_periodo = sum(appt.session_price for appt in financial_appointments if appt.session_price)
    total_recebido_periodo = sum(appt.amount_paid for appt in financial_appointments if appt.amount_paid)
    start_of_current_month = hoje.replace(day=1)
    appointments_this_month = db.session.query(Appointment).join(User).filter(User.clinic_id == current_user.id, Appointment.start_time >= start_of_current_month).all()
    status_counts = {'Concluído': 0, 'Agendado': 0, 'Cancelado': 0}
    for appt in appointments_this_month:
        if appt.status in status_counts: status_counts[appt.status] += 1
    return render_template('reports.html', financial_appointments=financial_appointments, total_cobrado=total_cobrado_periodo, total_recebido=total_recebido_periodo, start_date=start_date.strftime('%Y-%m-%d'), end_date=end_date.strftime('%Y-%m-%d'), status_counts=status_counts)

# ... (comandos init-db e main)
@app.cli.command("init-db")
def init_db_command():
    db.create_all()
    print("Banco de dados inicializado e tabelas criadas.")

if __name__ == '__main__':
    app.run(debug=True)
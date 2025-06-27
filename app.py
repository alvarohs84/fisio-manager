import os
from datetime import datetime, date, timedelta
import calendar
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy

# --- CONFIGURAÇÃO ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'uma-chave-secreta-muito-segura-e-diferente'

# Configuração do Banco de Dados SQLite
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'planner.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- MODELO DO BANCO DE DADOS ---
class Atendimento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_paciente = db.Column(db.String(100), nullable=False)
    data_atendimento = db.Column(db.Date, nullable=False)
    hora_atendimento = db.Column(db.Time, nullable=False)
    local = db.Column(db.String(150), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Agendado')

    def __repr__(self):
        return f'<Atendimento {self.nome_paciente} em {self.data_atendimento}>'

# --- COMANDO PARA INICIALIZAR O DB ---
@app.cli.command("init-db")
def init_db():
    """Cria todas as tabelas do banco de dados."""
    db.create_all()
    print("Banco de dados inicializado e tabelas criadas.")

# --- ROTAS PRINCIPAIS E DE VISUALIZAÇÃO ---
@app.route('/')
def index():
    """Mostra a visão geral e o formulário de navegação."""
    hoje = date.today()
    atendimentos = Atendimento.query.filter(Atendimento.data_atendimento >= hoje).order_by(Atendimento.data_atendimento, Atendimento.hora_atendimento).all()
    return render_template('index.html', atendimentos=atendimentos, hoje_str=hoje.strftime('%Y-%m-%d'))

@app.route('/agenda')
def agenda():
    """Renderiza a página que contém a agenda visual (FullCalendar)."""
    return render_template('agenda_grid.html')

@app.route('/dia/<date_str>')
def dia(date_str):
    """Mostra os atendimentos para um dia específico."""
    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    atendimentos = Atendimento.query.filter_by(data_atendimento=target_date).order_by(Atendimento.hora_atendimento).all()
    prev_day = (target_date - timedelta(days=1)).strftime('%Y-%m-%d')
    next_day = (target_date + timedelta(days=1)).strftime('%Y-%m-%d')
    return render_template('view_filtered.html', atendimentos=atendimentos, view_title=f"Dia: {target_date.strftime('%d/%m/%Y')}", prev_url=url_for('dia', date_str=prev_day), next_url=url_for('dia', date_str=next_day))

@app.route('/semana/<date_str>')
def semana(date_str):
    """Mostra os atendimentos para uma semana específica."""
    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    start_of_week = target_date - timedelta(days=target_date.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    atendimentos = Atendimento.query.filter(Atendimento.data_atendimento.between(start_of_week, end_of_week)).order_by(Atendimento.data_atendimento, Atendimento.hora_atendimento).all()
    prev_week_date = (start_of_week - timedelta(days=1)).strftime('%Y-%m-%d')
    next_week_date = (end_of_week + timedelta(days=1)).strftime('%Y-%m-%d')
    view_title = f"Semana: {start_of_week.strftime('%d/%m')} a {end_of_week.strftime('%d/%m/%Y')}"
    return render_template('view_filtered.html', atendimentos=atendimentos, view_title=view_title, prev_url=url_for('semana', date_str=prev_week_date), next_url=url_for('semana', date_str=next_week_date))

@app.route('/mes/<int:year>/<int:month>')
def mes(year, month):
    """Mostra os atendimentos para um mês e ano específicos."""
    start_of_month = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end_of_month = date(year, month, last_day)
    atendimentos = Atendimento.query.filter(Atendimento.data_atendimento.between(start_of_month, end_of_month)).order_by(Atendimento.data_atendimento, Atendimento.hora_atendimento).all()
    prev_month_date = start_of_month - timedelta(days=1)
    next_month_date = end_of_month + timedelta(days=1)
    locale_pt_br = calendar.LocaleHTMLCalendar(locale='pt_BR').formatmonthname(year, month, 0)
    view_title = f"Mês: {locale_pt_br.capitalize()}"
    return render_template('view_filtered.html', atendimentos=atendimentos, view_title=view_title, prev_url=url_for('mes', year=prev_month_date.year, month=prev_month_date.month), next_url=url_for('mes', year=next_month_date.year, month=next_month_date.month))

# --- ROTAS DE EDIÇÃO / CRIAÇÃO ---
@app.route('/add', methods=('GET', 'POST'))
def add():
    if request.method == 'POST':
        # (Lógica para adicionar atendimento)
        nome_paciente = request.form['nome_paciente']
        data_str = request.form['data_atendimento']
        hora_str = request.form['hora_atendimento']
        local = request.form['local']
        if not all([nome_paciente, data_str, hora_str, local]):
            flash('Todos os campos são obrigatórios!', 'error')
        else:
            novo_atendimento = Atendimento(
                nome_paciente=nome_paciente,
                data_atendimento=datetime.strptime(data_str, '%Y-%m-%d').date(),
                hora_atendimento=datetime.strptime(hora_str, '%H:%M').time(),
                local=local)
            db.session.add(novo_atendimento)
            db.session.commit()
            flash('Atendimento agendado com sucesso!', 'success')
            return redirect(url_for('index'))
    return render_template('add.html')

@app.route('/edit/<int:id>', methods=('GET', 'POST'))
def edit(id):
    atendimento = Atendimento.query.get_or_404(id)
    if request.method == 'POST':
        # (Lógica para editar atendimento)
        atendimento.nome_paciente = request.form['nome_paciente']
        atendimento.data_atendimento = datetime.strptime(request.form['data_atendimento'], '%Y-%m-%d').date()
        atendimento.hora_atendimento = datetime.strptime(request.form['hora_atendimento'], '%H:%M').time()
        atendimento.local = request.form['local']
        atendimento.status = request.form['status']
        db.session.commit()
        flash('Atendimento atualizado com sucesso!', 'success')
        return redirect(request.referrer or url_for('index'))
    return render_template('edit.html', atendimento=atendimento)

@app.route('/delete/<int:id>')
def delete(id):
    atendimento = Atendimento.query.get_or_404(id)
    db.session.delete(atendimento)
    db.session.commit()
    flash('Atendimento removido com sucesso!', 'success')
    return redirect(url_for('index'))

# --- API ENDPOINT PARA O FULLCALENDAR ---
@app.route('/api/atendimentos')
def api_atendimentos():
    """Retorna atendimentos em JSON para o FullCalendar."""
    atendimentos = Atendimento.query.all()
    eventos = [{
        'id': aten.id,
        'title': aten.nome_paciente,
        'start': f"{aten.data_atendimento.isoformat()}T{aten.hora_atendimento.isoformat()}",
        'url': url_for('edit', id=aten.id),
        'color': '#28a745' if aten.status == 'Concluído' else ('#ffc107' if aten.status == 'Confirmado' else '#17a2b8'),
        'borderColor': '#28a745' if aten.status == 'Concluído' else ('#ffc107' if aten.status == 'Confirmado' else '#17a2b8')
    } for aten in atendimentos]
    return jsonify(eventos)
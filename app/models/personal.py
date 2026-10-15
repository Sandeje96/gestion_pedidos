# -*- coding: utf-8 -*-
"""
Modelos para la gestión de Personal, Registro de Asistencia y Banco de Horas.
"""

from app import db
from datetime import datetime, date, time, timedelta


def formatear_minutos(minutos):
    """
    Convierte minutos enteros a formato legible con signo.
    Ejemplo:
        90  -> '+1h 30m'
        -45 -> '-45m'
        0   -> '0m'
    """
    if minutos is None:
        return '0m'
    signo = '+' if minutos > 0 else ('-' if minutos < 0 else '')
    abs_mins = abs(int(minutos))
    horas = abs_mins // 60
    resto = abs_mins % 60
    if horas > 0 and resto > 0:
        return f"{signo}{horas}h {resto:02d}m"
    elif horas > 0:
        return f"{signo}{horas}h 00m"
    elif resto > 0:
        return f"{signo}{resto}m"
    else:
        return "0m"


class Personal(db.Model):
    """
    Representa a un integrante del personal de fábrica.
    """
    __tablename__ = 'personal'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    apellido = db.Column(db.String(100), nullable=True, default='')
    dni = db.Column(db.String(20), nullable=True)
    telefono = db.Column(db.String(30), nullable=True)
    puesto = db.Column(db.String(100), nullable=True, default='Fábrica / Producción')

    # Horario habitual de lunes a viernes (por defecto 08:00 a 17:00 = 9 horas)
    hora_ingreso_habitual = db.Column(db.String(5), nullable=False, default='08:00')
    hora_salida_habitual = db.Column(db.String(5), nullable=False, default='17:00')

    # Configuración de sábados
    trabaja_sabados = db.Column(db.Boolean, nullable=False, default=True)
    hora_ingreso_sabado = db.Column(db.String(5), nullable=False, default='08:00')
    hora_salida_sabado = db.Column(db.String(5), nullable=False, default='17:00')

    # Saldo inicial manual de banco de horas (en minutos)
    saldo_inicial_minutos = db.Column(db.Integer, nullable=False, default=0)

    activo = db.Column(db.Boolean, nullable=False, default=True)
    notas = db.Column(db.Text, nullable=True)
    fecha_ingreso = db.Column(db.Date, nullable=False, default=date.today)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_actualizacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relación con registros de asistencia
    asistencias = db.relationship(
        'RegistroAsistencia',
        backref='personal',
        cascade='all, delete-orphan',
        order_by='RegistroAsistencia.fecha.desc()',
        lazy='dynamic'
    )

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido}".strip()

    def get_saldo_banco_minutos(self):
        """
        Calcula el saldo acumulado total del banco de horas en minutos.
        Saldo = saldo_inicial + sum(diferencia_minutos de todas las asistencias registradas).
        Positivo: horas a favor del empleado.
        Negativo: horas adeudadas por el empleado.
        """
        total_difs = db.session.query(
            db.func.coalesce(db.func.sum(RegistroAsistencia.diferencia_minutos), 0)
        ).filter(
            RegistroAsistencia.personal_id == self.id
        ).scalar() or 0

        return int(self.saldo_inicial_minutos or 0) + int(total_difs)

    @property
    def saldo_formateado(self):
        return formatear_minutos(self.get_saldo_banco_minutos())

    @property
    def saldo_estado(self):
        s = self.get_saldo_banco_minutos()
        if s > 0:
            return 'a_favor'
        elif s < 0:
            return 'adeudado'
        return 'al_dia'

    def get_horario_pactado_para_fecha(self, fecha_obj):
        """
        Devuelve (hora_ingreso, hora_salida, minutos_esperados) según si es sábado o lunes-viernes.
        Si es domingo o no trabaja sábados, minutos_esperados = 0.
        """
        w = fecha_obj.weekday()
        if w == 6:  # Domingo
            return (None, None, 0)
        elif w == 5:  # Sábado
            if not self.trabaja_sabados:
                return (None, None, 0)
            ing = self.hora_ingreso_sabado or '08:00'
            sal = self.hora_salida_sabado or '17:00'
        else:  # Lunes a Viernes
            ing = self.hora_ingreso_habitual or '08:00'
            sal = self.hora_salida_habitual or '17:00'

        mins = RegistroAsistencia.calcular_minutos_entre(ing, sal)
        return (ing, sal, mins)

    def to_dict(self):
        saldo_mins = self.get_saldo_banco_minutos()
        return {
            'id': self.id,
            'nombre': self.nombre,
            'apellido': self.apellido or '',
            'nombre_completo': self.nombre_completo,
            'dni': self.dni or '',
            'telefono': self.telefono or '',
            'puesto': self.puesto or '',
            'hora_ingreso_habitual': self.hora_ingreso_habitual,
            'hora_salida_habitual': self.hora_salida_habitual,
            'trabaja_sabados': self.trabaja_sabados,
            'hora_ingreso_sabado': self.hora_ingreso_sabado,
            'hora_salida_sabado': self.hora_salida_sabado,
            'saldo_banco_minutos': saldo_mins,
            'saldo_formateado': formatear_minutos(saldo_mins),
            'saldo_estado': 'a_favor' if saldo_mins > 0 else ('adeudado' if saldo_mins < 0 else 'al_dia'),
            'activo': self.activo,
            'notas': self.notas or '',
        }


class RegistroAsistencia(db.Model):
    """
    Registro diario de asistencia, ingreso y salida de un integrante del personal.
    Permite calcular las horas trabajadas vs esperadas y la diferencia para el banco de horas.
    """
    __tablename__ = 'asistencias_personal'

    id = db.Column(db.Integer, primary_key=True)
    personal_id = db.Column(db.Integer, db.ForeignKey('personal.id'), nullable=False, index=True)
    fecha = db.Column(db.Date, nullable=False, index=True)

    # Horarios reales informados
    hora_ingreso = db.Column(db.String(5), nullable=True)  # '08:00'
    hora_salida = db.Column(db.String(5), nullable=True)   # '17:00'

    # Horarios pactados para ese día específico
    hora_ingreso_pactada = db.Column(db.String(5), nullable=False, default='08:00')
    hora_salida_pactada = db.Column(db.String(5), nullable=False, default='17:00')

    # Cálculos en minutos
    minutos_trabajados = db.Column(db.Integer, nullable=False, default=0)
    minutos_esperados = db.Column(db.Integer, nullable=False, default=540)
    diferencia_minutos = db.Column(db.Integer, nullable=False, default=0)

    # Tipo de registro:
    # 'normal': Jornada de trabajo estándar
    # 'compensacion': Día acordado para compensar horas (entrando más tarde o saliendo antes)
    # 'franco': Día de descanso
    # 'ausente_justificado': Falta con justificativo (sin descuento de banco)
    # 'ausente_injustificado': Falta no justificada (resta las horas esperadas del banco)
    # 'feriado': Feriado no laborable
    tipo_dia = db.Column(db.String(30), nullable=False, default='normal')

    observaciones = db.Column(db.Text, nullable=True)
    registrado_por_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)

    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_actualizacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('personal_id', 'fecha', name='uq_personal_fecha'),
    )

    @staticmethod
    def calcular_minutos_entre(hora_ini_str, hora_fin_str):
        """
        Calcula la cantidad de minutos entre dos horas en formato 'HH:MM'.
        Soporta turnos que crucen medianoche si correspondiera.
        """
        if not hora_ini_str or not hora_fin_str:
            return 0
        try:
            h_ini, m_ini = map(int, hora_ini_str.strip().split(':'))
            h_fin, m_fin = map(int, hora_fin_str.strip().split(':'))
            t_ini = h_ini * 60 + m_ini
            t_fin = h_fin * 60 + m_fin
            if t_fin < t_ini:
                # Cruza medianoche
                return (24 * 60 - t_ini) + t_fin
            return t_fin - t_ini
        except Exception:
            return 0

    def recalcular(self):
        """
        Recalcula minutos_trabajados, minutos_esperados y diferencia_minutos
        según horarios y tipo_dia.
        """
        if self.tipo_dia in ('franco', 'feriado', 'ausente_justificado'):
            self.minutos_esperados = 0
            self.minutos_trabajados = self.calcular_minutos_entre(self.hora_ingreso, self.hora_salida)
            self.diferencia_minutos = self.minutos_trabajados
            return

        if self.tipo_dia == 'ausente_injustificado':
            self.minutos_trabajados = 0
            self.minutos_esperados = self.calcular_minutos_entre(self.hora_ingreso_pactada, self.hora_salida_pactada) or 540
            self.diferencia_minutos = -self.minutos_esperados
            return

        # Para 'normal' o 'compensacion':
        self.minutos_esperados = self.calcular_minutos_entre(self.hora_ingreso_pactada, self.hora_salida_pactada) or 540
        if self.hora_ingreso and self.hora_salida:
            self.minutos_trabajados = self.calcular_minutos_entre(self.hora_ingreso, self.hora_salida)
            self.diferencia_minutos = self.minutos_trabajados - self.minutos_esperados
        else:
            self.minutos_trabajados = 0
            self.diferencia_minutos = 0

    @property
    def diferencia_formateada(self):
        return formatear_minutos(self.diferencia_minutos)

    @property
    def horas_trabajadas_formateadas(self):
        mins = self.minutos_trabajados or 0
        return f"{mins // 60}h {mins % 60:02d}m"

    @property
    def horas_esperadas_formateadas(self):
        mins = self.minutos_esperados or 0
        return f"{mins // 60}h {mins % 60:02d}m"

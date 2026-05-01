"""
Tests del motor OCR y de la lógica multi-tenant.

Para ejecutar:
    python manage.py test gastos
"""
from datetime import datetime
from django.test import TestCase
from django.contrib.auth.models import User

from gastos.models import Empresa, PerfilUsuario, Obra, Gasto
from gastos.utils import (
    es_rut_valido,
    formatear_rut,
    _extraer_fecha,
    _extraer_folio,
    _extraer_monto_total,
)


class TestRutValidator(TestCase):

    def test_ruts_invalidos(self):
        casos = ["", None, "abc", "123", "12345678-Z"]
        for rut in casos:
            with self.subTest(rut=rut):
                self.assertFalse(es_rut_valido(rut))

    def test_formatear_rut(self):
        self.assertEqual(formatear_rut("76.123.456-7"), "76123456-7")
        self.assertEqual(formatear_rut("76 123 456 - 7"), "76123456-7")
        self.assertIsNone(formatear_rut(None))


class TestExtraerFecha(TestCase):

    def test_fecha_formato_texto(self):
        anio = datetime.now().year
        texto = f"BOLETA EMITIDA EL 15 DE MARZO DE {anio}"
        self.assertEqual(_extraer_fecha(texto), f"{anio}-03-15")

    def test_fecha_numerica(self):
        anio = datetime.now().year
        texto = f"FECHA: 15-03-{anio}"
        self.assertEqual(_extraer_fecha(texto), f"{anio}-03-15")

    def test_no_hardcodea_2026(self):
        anio_pasado = datetime.now().year - 1
        texto = f"FACTURA DEL 10 DE ENERO DE {anio_pasado}"
        fecha = _extraer_fecha(texto)
        self.assertIsNotNone(fecha)
        self.assertIn(str(anio_pasado), fecha)


class TestExtraerFolio(TestCase):

    def test_folio_simple(self):
        palabras = ["FOLIO", "12345"]
        self.assertEqual(_extraer_folio(palabras, "FOLIO 12345"), "12345")

    def test_folio_preserva_ceros(self):
        palabras = ["FOLIO", "00123"]
        self.assertEqual(_extraer_folio(palabras, "FOLIO 00123"), "00123")

    def test_no_confunde_con_rut(self):
        palabras = ["FOLIO", "76123456-7"]
        self.assertIsNone(_extraer_folio(palabras, "FOLIO 76123456-7"))


class TestExtraerMonto(TestCase):

    def test_con_palabra_clave(self):
        palabras = ["TOTAL", "PAGAR", "1.234.567"]
        monto = _extraer_monto_total("TOTAL A PAGAR 1.234.567", palabras)
        self.assertEqual(monto, 1234567)

    def test_sin_palabra_usa_max(self):
        palabras = ["VALOR", "1.000", "OTRO", "5.000"]
        monto = _extraer_monto_total("VALOR 1.000 OTRO 5.000", palabras)
        self.assertEqual(monto, 5000)


class TestMultiTenantSecurity(TestCase):
    """Verifica que un usuario no pueda ver/editar/borrar datos de otra empresa."""

    def setUp(self):
        self.empresa_a = Empresa.objects.create(nombre="Empresa A")
        self.user_a = User.objects.create_user(username="usera", password="test123")
        PerfilUsuario.objects.create(user=self.user_a, empresa=self.empresa_a)
        self.gasto_a = Gasto.objects.create(
            usuario=self.user_a, empresa=self.empresa_a,
            monto_total=100000, imagen='boletas/test.jpg'
        )

        self.empresa_b = Empresa.objects.create(nombre="Empresa B")
        self.user_b = User.objects.create_user(username="userb", password="test123")
        PerfilUsuario.objects.create(user=self.user_b, empresa=self.empresa_b)
        self.gasto_b = Gasto.objects.create(
            usuario=self.user_b, empresa=self.empresa_b,
            monto_total=200000, imagen='boletas/test2.jpg'
        )

    def test_get_gastos_aisla(self):
        from gastos.views import get_gastos_empresa
        self.assertEqual(get_gastos_empresa(self.user_a).count(), 1)
        self.assertEqual(get_gastos_empresa(self.user_a).first().empresa, self.empresa_a)

    def test_a_no_puede_editar_gasto_de_b(self):
        self.client.login(username='usera', password='test123')
        response = self.client.get(f'/editar/{self.gasto_b.id}/')
        self.assertEqual(response.status_code, 404)

    def test_a_no_puede_eliminar_gasto_de_b(self):
        self.client.login(username='usera', password='test123')
        self.client.post(f'/eliminar/{self.gasto_b.id}/')
        self.assertTrue(Gasto.objects.filter(id=self.gasto_b.id).exists())

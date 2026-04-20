# gastos/urls.py
from django.urls import path
from . import views
from django.contrib.auth.views import LoginView, LogoutView

urlpatterns = [
    path('login/', LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('', views.dashboard, name='dashboard'),
    path('eliminar/<int:pk>/', views.eliminar_gasto, name='eliminar_gasto'),
    path('nuevo/', views.crear_gasto, name='crear_gasto'),
    path('editar/<int:pk>/', views.editar_gasto, name='editar_gasto'),
    path('carga-masiva/', views.carga_masiva, name='carga_masiva'),
    path('eliminar/<int:pk>/', views.eliminar_gasto, name='eliminar_gasto'),
    path('historial/', views.historial_gastos, name='historial_gastos'),
    path('proyectos/', views.lista_obras, name='lista_obras'),
    path('proyectos/nuevo/', views.crear_obra, name='crear_obra'),
    path('presupuesto/<int:obra_id>/', views.definir_presupuesto, name='definir_presupuesto'),
    path('eliminar-masivo/', views.eliminar_masivo, name='eliminar_masivo'),
    path('exportar-excel/', views.exportar_excel, name='exportar_excel'),
    path('exportar-pdf/', views.exportar_pdf, name='exportar_pdf'),
    path('gasto/<int:pk>/descargar-pdf/', views.descargar_boleta_pdf, name='descargar_pdf'),
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
]
# gastos/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('eliminar/<int:pk>/', views.eliminar_gasto, name='eliminar_gasto'),
    path('nuevo/', views.crear_gasto, name='crear_gasto'),
    path('editar/<int:pk>/', views.editar_gasto, name='editar_gasto'),
    path('carga-masiva/', views.carga_masiva, name='carga_masiva'),
    path('eliminar/<int:pk>/', views.eliminar_gasto, name='eliminar_gasto'),
    path('historial/', views.historial_gastos, name='historial_gastos'),
    path('eliminar-masivo/', views.eliminar_masivo, name='eliminar_masivo'),
    path('exportar-excel/', views.exportar_excel, name='exportar_excel'),
    path('exportar-pdf/', views.exportar_pdf, name='exportar_pdf'),
]
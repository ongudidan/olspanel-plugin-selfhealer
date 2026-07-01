from django.urls import path
from . import views

urlpatterns = [
    path('gui/', views.self_healer_gui, name='self_healer_gui'),
    path('run/', views.self_healer_run, name='self_healer_run'),
]

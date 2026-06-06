from django.urls import path
from vehicles import views

urlpatterns = [
    path('vahaan-lookup/', views.vahaan_lookup, name='vahaan_lookup'),
    path('list-car/',      views.list_car,      name='list_car'),
    path('my-cars/',       views.my_cars,       name='my_cars'),
]

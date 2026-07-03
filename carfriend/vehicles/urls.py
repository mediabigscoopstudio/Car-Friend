from django.urls import path
from vehicles import views

urlpatterns = [
    path('vahaan-lookup/', views.vahaan_lookup, name='vahaan_lookup'),
    path('list-car/',      views.list_car,      name='list_car'),
    path('my-cars/',       views.my_cars,       name='my_cars'),
    # Guest sell flow (AJAX)
    path('sell/send-otp/',   views.sell_send_otp,   name='sell_send_otp'),
    path('sell/verify-otp/', views.sell_verify_otp, name='sell_verify_otp'),
    path('sell/estimate/',   views.sell_estimate,   name='sell_estimate'),
    # Seller car detail + journey pages (numeric — never shadows the routes above)
    path('<int:pk>/',            views.car_detail,     name='car_detail'),
    path('<int:pk>/inspection/', views.car_inspection, name='car_inspection'),
    path('<int:pk>/documents/',  views.car_documents,  name='car_documents'),
]

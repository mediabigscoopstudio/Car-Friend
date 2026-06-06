import json
from datetime import date
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from vehicles.models import Vehicle


# ── Mock Vahaan data ──────────────────────────────────────────────────────────

MOCK_VAHAAN_DB = {
    'GJ05MK2024': {
        'found':               True,
        'plate_number':        'GJ05MK2024',
        'make':                'Mahindra',
        'model':               'Scorpio N',
        'variant':             'Z8',
        'year':                2024,
        'fuel_type':           'diesel',
        'transmission':        'automatic',
        'colour':              'Deep Forest Green',
        'registration_date':   '2024-03-15',
        'registration_state':  'Gujarat',
        'rto':                 'Ahmedabad (GJ-05)',
        'owner_name':          'Minaketan Mishra',
        'owner_number':        1,
        'chassis_number':      'MA1RB3HJXP1234567',
        'engine_number':       'mHAWK140P1234567',
        'insurance_valid_till': '2027-03-14',
        'is_hypothecated':     False,
        'accident_history':    False,
    }
}


def normalise_plate(plate):
    return plate.upper().replace(' ', '').replace('-', '')


def vahaan_lookup(request):
    if request.method != 'POST':
        return JsonResponse({'found': False, 'error': 'POST required'}, status=405)

    try:
        body = json.loads(request.body)
        plate = normalise_plate(body.get('plate_number', ''))
    except (json.JSONDecodeError, AttributeError):
        plate = normalise_plate(request.POST.get('plate_number', ''))

    data = MOCK_VAHAAN_DB.get(plate)

    if data:
        if Vehicle.objects.filter(plate_number=plate).exists():
            return JsonResponse({
                'found': False,
                'error': 'This vehicle is already listed on CarFriend.'
            })
        return JsonResponse(data)

    return JsonResponse({
        'found': False,
        'error': 'Vehicle not found. Please check the number plate and try again.'
    })


@login_required(login_url='/auth/login/')
def list_car(request):
    if not request.user.is_seller:
        return redirect('/auth/seller/dashboard/')

    if request.method == 'POST':
        plate = normalise_plate(request.POST.get('plate_number', ''))

        if Vehicle.objects.filter(plate_number=plate).exists():
            messages.error(request, 'This vehicle is already listed on CarFriend.')
            return redirect('seller_dashboard')

        def parse_date(val):
            try:
                return date.fromisoformat(val) if val else None
            except ValueError:
                return None

        def parse_bool(val):
            return val in ('true', 'True', '1', 'yes', 'on')

        vehicle = Vehicle.objects.create(
            seller                    = request.user,
            plate_number              = plate,
            make                      = request.POST.get('make', ''),
            model                     = request.POST.get('model', ''),
            variant                   = request.POST.get('variant', ''),
            year                      = int(request.POST.get('year', 2020)),
            fuel_type                 = request.POST.get('fuel_type', 'petrol'),
            transmission              = request.POST.get('transmission', 'manual'),
            colour                    = request.POST.get('colour', ''),
            registration_date         = parse_date(request.POST.get('registration_date')),
            registration_state        = request.POST.get('registration_state', ''),
            rto                       = request.POST.get('rto', ''),
            owner_name                = request.POST.get('owner_name', ''),
            owner_number              = int(request.POST.get('owner_number', 1)),
            chassis_number            = request.POST.get('chassis_number', ''),
            engine_number             = request.POST.get('engine_number', ''),
            insurance_valid_till      = parse_date(request.POST.get('insurance_valid_till')),
            is_hypothecated           = parse_bool(request.POST.get('is_hypothecated', 'false')),
            accident_history          = parse_bool(request.POST.get('accident_history', 'false')),
            odometer_km               = int(request.POST.get('odometer_km', 0) or 0) or None,
            last_service_date         = parse_date(request.POST.get('last_service_date')),
            tyre_condition            = request.POST.get('tyre_condition', ''),
            expected_price            = request.POST.get('expected_price') or None,
            city                      = request.POST.get('city', ''),
            inspection_address        = request.POST.get('inspection_address', ''),
            preferred_inspection_slot = request.POST.get('preferred_inspection_slot', ''),
            status                    = Vehicle.STATUS_SUBMITTED,
        )

        for field in ['rc_document', 'insurance_document', 'service_history', 'noc_document']:
            f = request.FILES.get(field)
            if f:
                setattr(vehicle, field, f)
        vehicle.save()

        messages.success(
            request,
            f'Your {vehicle.display_name} has been listed! Our team will schedule an inspection shortly.'
        )
        return redirect('seller_dashboard')

    return render(request, 'www/vehicles/list_car.html')


@login_required(login_url='/auth/login/')
def my_cars(request):
    vehicles = Vehicle.objects.filter(seller=request.user)
    data = [{
        'id':                      v.id,
        'display_name':            v.display_name,
        'plate_number':            v.plate_number,
        'year':                    v.year,
        'fuel_type':               v.get_fuel_type_display(),
        'odometer_km':             v.odometer_km,
        'city':                    v.city,
        'status':                  v.status,
        'status_label':            v.status_label,
        'expected_price':          str(v.expected_price) if v.expected_price else None,
        'inspection_report_ready': v.inspection_report_ready,
        'auction_active':          v.auction_active,
        'created_at':              v.created_at.strftime('%d %b %Y'),
    } for v in vehicles]
    return JsonResponse({'vehicles': data})

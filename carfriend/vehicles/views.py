import json
from datetime import date
from urllib.parse import urlencode
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login as auth_login
from django.http import JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from vehicles.models import Vehicle

from www import otp, pricing, services
from accounts.guest import (
    get_or_create_guest_user,
    merge_guest_cars_into,
    normalise_phone,
)

# Session keys for the guest sell flow
SESS_CAR = "sell_car"          # full (server-only) lookup result incl. real owner name
SESS_VERIFIED = "sell_phone"   # verified phone for the in-progress sale


def mask_owner_name(name):
    """Mask a registered owner's name for display — never send the full name to
    the client. e.g. "Minaketan Mishra" -> "M•••••••• M•••••"."""
    parts = (name or "").split()
    masked = []
    for p in parts:
        masked.append(p[0] + "•" * (len(p) - 1) if len(p) > 1 else p)
    return " ".join(masked) or "—"


def normalise_plate(plate):
    return (plate or '').upper().replace(' ', '').replace('-', '')


def vahaan_lookup(request):
    """Look the plate up via the real Surepass RC API (www/services.py).

    The full record (with the real owner name) is kept server-side in the
    session; the client receives a copy with the owner name MASKED.
    """
    if request.method != 'POST':
        return JsonResponse({'found': False, 'error': 'POST required'}, status=405)

    try:
        body = json.loads(request.body)
        plate = normalise_plate(body.get('plate_number', ''))
    except (json.JSONDecodeError, AttributeError):
        plate = normalise_plate(request.POST.get('plate_number', ''))

    if not plate:
        return JsonResponse({'found': False, 'error': 'Please enter a number plate.'})

    if Vehicle.objects.filter(plate_number=plate).exists():
        return JsonResponse({'found': False, 'error': 'This vehicle is already listed on CarFriend.'})

    try:
        data = services.lookup_rc_full(plate)
    except services.SurepassNotFound:
        return JsonResponse({'found': False, 'error': 'Vehicle not found. Please check the number plate and try again.'})
    except services.SurepassTimeout:
        return JsonResponse({'found': False, 'error': 'The lookup service is slow right now. Please try again.'})
    except services.SurepassConfigError:
        return JsonResponse({'found': False, 'error': 'Lookup is temporarily unavailable. Please try again later.'})
    except services.SurepassError:
        return JsonResponse({'found': False, 'error': 'Something went wrong fetching your car. Please try again.'})

    data['found'] = True
    data['plate_number'] = plate
    # Keep the FULL record (incl. the real owner name) server-side only.
    request.session[SESS_CAR] = data
    request.session.modified = True
    # Send a copy to the client with the owner name MASKED.
    public = dict(data)
    public['owner_name'] = mask_owner_name(data.get('owner_name', ''))
    public['owner_name_masked'] = True
    return JsonResponse(public)


@ensure_csrf_cookie
def list_car(request):
    # Public sell flow — guests allowed (a phone-keyed account is created after
    # OTP). The legacy full-form POST path stays for authenticated sellers.
    # @ensure_csrf_cookie guarantees the csrftoken cookie is set for the AJAX JS.
    if request.method == 'POST' and request.user.is_authenticated and getattr(request.user, 'is_seller', False):
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

    ctx = {'km_bands': pricing.KM_BANDS}
    # Existing Google login (allauth) for the verify step. ?next returns the
    # visitor to the sell flow, where the session-kept car resumes the steps.
    ctx['google_login_url'] = '/accounts/google/login/?' + urlencode(
        {'process': 'login', 'next': '/vehicles/list-car/'})
    # If the visitor came from the homepage hero, a lookup already populated the
    # session — hand the (masked) car to the template so the flow resumes at the
    # Car Details step instead of asking for the plate again.
    car = request.session.get(SESS_CAR)
    if car:
        ctx['prefill_car'] = json.dumps({
            'plate_number':         car.get('plate_number', ''),
            'make':                 car.get('make', ''),
            'model':                car.get('model', ''),
            'variant':              car.get('variant', ''),
            'year':                 car.get('year', ''),
            'fuel_type':            car.get('fuel_type', ''),
            'transmission':         car.get('transmission', ''),
            'colour':               car.get('colour', ''),
            'rto':                  car.get('rto', ''),
            'registration_state':   car.get('registration_state', ''),
            'owner_name':           mask_owner_name(car.get('owner_name', '')),
            'owner_number':         car.get('owner_number', 1),
            'insurance_valid_till': car.get('insurance_valid_till', ''),
        })
    return render(request, 'www/vehicles/list_car.html', ctx)


@login_required(login_url='/auth/login/')
def my_cars(request):
    # Pull in any guest cars that match this account's verified phone.
    merge_guest_cars_into(request.user)
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


# ── Guest sell flow: OTP → estimate → phone-keyed account ─────────────────────

def _json_body(request):
    try:
        return json.loads(request.body or b"{}")
    except (json.JSONDecodeError, TypeError):
        return {}


def _parse_date(val):
    try:
        return date.fromisoformat(val) if val else None
    except (ValueError, TypeError):
        return None


@require_POST
def sell_send_otp(request):
    """Send an OTP to the seller's phone (stub or real per FAST2SMS_API_KEY)."""
    phone = normalise_phone(_json_body(request).get('phone'))
    if len(phone) != 10 or phone[0] not in '6789':
        return JsonResponse({'ok': False, 'error': 'Enter a valid 10-digit mobile number.'}, status=400)
    try:
        result = otp.send_otp(phone)
    except otp.OTPRateLimited as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=429)
    except otp.OTPError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=502)
    # Never leak the code; only the mode (so the UI can hint "use 000000" in stub).
    return JsonResponse({'ok': True, 'stub': result['mode'] == 'stub'})


@require_POST
def sell_verify_otp(request):
    """Verify the OTP, then create/find the phone-keyed account and sign in."""
    body = _json_body(request)
    phone = normalise_phone(body.get('phone'))
    code = (body.get('code') or '').strip()
    if not otp.verify_otp(phone, code):
        return JsonResponse({'ok': False, 'error': 'Incorrect or expired OTP. Please try again.'}, status=400)

    user = get_or_create_guest_user(phone)
    # Explicit backend required because the project configures multiple
    # AUTHENTICATION_BACKENDS (ModelBackend + allauth).
    auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    request.session[SESS_VERIFIED] = phone
    request.session.modified = True
    return JsonResponse({'ok': True})


@require_POST
def sell_estimate(request):
    """Compute the price estimate and persist the car + lead under the
    phone-keyed account. Requires a verified phone (OTP) in the session."""
    car = request.session.get(SESS_CAR)
    phone = request.session.get(SESS_VERIFIED)
    # Authenticated users (e.g. signed in with Google) are already verified — no
    # OTP needed. Anonymous users still must have a verified phone in session.
    if not phone and request.user.is_authenticated:
        phone = request.user.phone or ""
    if not car or (not phone and not request.user.is_authenticated):
        return JsonResponse({'ok': False, 'error': 'Please verify your phone first.'}, status=403)

    body = _json_body(request)
    band_key = (body.get('km_band') or '').strip()
    if not pricing.band_midpoint(band_key):
        return JsonResponse({'ok': False, 'error': 'Please select how many kilometres the car has run.'}, status=400)

    # Variant + fuel are editable on the Car Details screen; honour edits for
    # both the estimate and the saved record.
    variant = body.get('variant')
    variant = variant.strip() if isinstance(variant, str) else car.get('variant', '')
    valid_fuels = {c[0] for c in Vehicle.FUEL_CHOICES}
    fuel = (body.get('fuel') or car.get('fuel_type') or Vehicle.FUEL_PETROL).lower()
    if fuel not in valid_fuels:
        fuel = Vehicle.FUEL_PETROL

    estimate = pricing.compute_estimate(
        car.get('make'), car.get('model'), variant, car.get('year'), band_key)

    user = request.user if request.user.is_authenticated else get_or_create_guest_user(phone)
    plate = normalise_plate(car.get('plate_number', ''))

    # Persist the car (real owner name from the server-side session, never the
    # masked client copy) under the account. Idempotent on plate.
    vehicle, created = Vehicle.objects.get_or_create(
        plate_number=plate,
        defaults=dict(
            seller=user,
            make=car.get('make', ''),
            model=car.get('model', ''),
            variant=variant,
            year=int(car.get('year') or pricing.CURRENT_YEAR),
            fuel_type=fuel,
            transmission=(car.get('transmission') or Vehicle.TRANSMISSION_MANUAL),
            colour=car.get('colour', ''),
            registration_date=_parse_date(car.get('registration_date')),
            registration_state=car.get('registration_state', ''),
            rto=car.get('rto', ''),
            owner_name=car.get('owner_name', ''),         # real name, server-side only
            owner_number=int(car.get('owner_number') or 1),
            chassis_number=car.get('chassis_number', ''),
            engine_number=car.get('engine_number', ''),
            insurance_valid_till=_parse_date(car.get('insurance_valid_till')),
            is_hypothecated=bool(car.get('is_hypothecated')),
            accident_history=bool(car.get('accident_history')),
            odometer_km=estimate['actual_km'],
            expected_price=estimate['value'],
            status=Vehicle.STATUS_SUBMITTED,             # triggers crm.Lead via signal
        ),
    )

    band_label = next((b['label'] for b in pricing.KM_BANDS if b['key'] == band_key), '')
    return JsonResponse({
        'ok': True,
        'estimate': {'low': estimate['low'], 'high': estimate['high']},
        'car': {
            'make': vehicle.make, 'model': vehicle.model, 'variant': vehicle.variant,
            'year': vehicle.year, 'fuel_type': vehicle.get_fuel_type_display(),
            'owner_name': mask_owner_name(vehicle.owner_name),  # masked for display
            'km_band': band_label,
        },
        'already_listed': not created,
        'phone': phone,
    })

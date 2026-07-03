import json
from datetime import date
from urllib.parse import urlencode
from django.shortcuts import render, redirect, get_object_or_404
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
    from django.utils import timezone
    from inspections.models import InspectionReport
    from auctions.models import Auction

    merge_guest_cars_into(request.user)
    vehicles = list(Vehicle.objects.filter(seller=request.user))
    vids = [v.id for v in vehicles]

    # Inspection report is "ready" for the seller when admin has APPROVED it
    # (InspectionReport.decision == 'approved') and a viewable PDF exists. The
    # internal inspector report page is inspector-only, so we link the seller to
    # the report PDF (served from /media/), which they can open.
    report_url_by_vehicle = {}
    for r in (InspectionReport.objects
              .filter(visit__vehicle_id__in=vids, decision='approved')
              .select_related('visit')
              .order_by('visit__vehicle_id', '-id')):
        vid = r.visit.vehicle_id
        if vid not in report_url_by_vehicle and r.pdf:
            report_url_by_vehicle[vid] = r.pdf.url

    # Auctions: a live one (status 'live' inside its window) → "Go to Auction";
    # otherwise, if any auction has finished → "ended".
    now = timezone.now()
    live_auction_id = {}
    ended_vehicles = set()
    for a in Auction.objects.filter(vehicle_id__in=vids):
        if a.status == 'live' and a.start_at <= now < a.end_at:
            live_auction_id.setdefault(a.vehicle_id, a.id)
        elif a.end_at <= now or a.status in ('ended', 'closed'):
            ended_vehicles.add(a.vehicle_id)

    data = []
    for v in vehicles:
        report_url = report_url_by_vehicle.get(v.id)
        auction_id = live_auction_id.get(v.id)
        if auction_id:
            auction_status = 'live'
        elif v.id in ended_vehicles:
            auction_status = 'ended'
        else:
            auction_status = None
        data.append({
            'id':                      v.id,
            'display_name':            v.display_name,
            'plate_number':            v.plate_number,
            'year':                    v.year,
            'fuel_type':               v.get_fuel_type_display(),
            'odometer_km':             v.odometer_km,
            'city':                    v.city,
            'status':                  v.status,
            'status_label':            v.status_label,
            'grade':                   v.condition_grade or None,
            'expected_price':          str(v.expected_price) if v.expected_price else None,
            'inspection_report_ready': bool(report_url),
            'report_url':              report_url,
            'auction_active':          bool(auction_id),
            'auction_id':              auction_id,
            'auction_status':          auction_status,
            'created_at':              v.created_at.strftime('%d %b %Y'),
        })
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


# ── Seller car detail / inspection / documents ────────────────────────────────

# The seller journey stages (mirrors the JS on the My Cars dashboard).
SELLER_STAGES = ['Listed', 'Inspected', 'Approved', 'Auction', 'Sold']
_STAGE_BY_STATUS = {
    'draft': 0, 'submitted': 0, 'inspection_scheduled': 1, 'inspection_done': 1,
    'approved': 2, 'in_auction': 3, 'sold': 4,
}


def _journey_stages(status):
    """Build (stages, step_of) for the server-rendered journey partial."""
    cur = _STAGE_BY_STATUS.get(status)   # None for 'rejected'
    stages = []
    for i, label in enumerate(SELLER_STAGES):
        if cur is not None and i < cur:
            state = 'done'
        elif i == cur:
            state = 'current'
        else:
            state = 'todo'
        stages.append({'label': label, 'state': state})
    step_of = None if cur is None else f'Step {cur + 1} of {len(SELLER_STAGES)}'
    return stages, step_of


def _seller_vehicle_or_404(request, pk):
    return get_object_or_404(Vehicle, pk=pk, seller=request.user)


@login_required(login_url='/auth/login/')
def car_detail(request, pk):
    from django.utils import timezone
    from inspections.models import InspectionReport
    from auctions.models import Auction
    from deals.models import Deal

    v = _seller_vehicle_or_404(request, pk)

    report = (InspectionReport.objects.filter(visit__vehicle=v, decision='approved')
              .select_related('visit').order_by('-id').first())
    report_url = report.pdf.url if report and report.pdf else None

    now = timezone.now()
    auctions = list(Auction.objects.filter(vehicle=v).order_by('-id'))
    live_auction = next((a for a in auctions
                         if a.status == 'live' and a.start_at <= now < a.end_at), None)
    latest_auction = auctions[0] if auctions else None
    decidable_auction = next((a for a in auctions
                              if a.status in ('closed', 'reauction', 'completed')), None)
    deal = Deal.objects.filter(vehicle=v, seller=request.user).order_by('-id').first()

    stages, step_of = _journey_stages(v.status)
    return render(request, 'www/vehicles/car_detail.html', {
        'v': v,
        'report': report,
        'report_url': report_url,
        'kyc_ok': request.user.is_kyc_done,
        'live_auction': live_auction,
        'latest_auction': latest_auction,
        'decidable_auction': decidable_auction,
        'deal': deal,
        'stages': stages,
        'step_of': step_of,
        'docs': {
            'rc': bool(v.rc_document), 'insurance': bool(v.insurance_document),
            'service': bool(v.service_history), 'noc': bool(v.noc_document),
        },
    })


@login_required(login_url='/auth/login/')
def car_inspection(request, pk):
    from inspections.models import InspectionReport

    v = _seller_vehicle_or_404(request, pk)
    report = (InspectionReport.objects.filter(visit__vehicle=v)
              .select_related('visit').order_by('-id').first())
    approved = report if (report and report.decision == 'approved') else None
    report_url = approved.pdf.url if approved and approved.pdf else None
    stages, step_of = _journey_stages(v.status)
    return render(request, 'www/vehicles/inspection.html', {
        'v': v, 'report': report, 'approved': approved, 'report_url': report_url,
        'stages': stages, 'step_of': step_of,
    })


@login_required(login_url='/auth/login/')
def car_documents(request, pk):
    v = _seller_vehicle_or_404(request, pk)
    if request.method == 'POST':
        changed = []
        for field in ['rc_document', 'insurance_document', 'service_history', 'noc_document']:
            f = request.FILES.get(field)
            if f:
                setattr(v, field, f)
                changed.append(field)
        if changed:
            v.save(update_fields=changed + ['updated_at'])
        return redirect('car_documents', pk=v.pk)
    return render(request, 'www/vehicles/documents.html', {
        'v': v,
        'docs': {
            'rc': v.rc_document or None, 'insurance': v.insurance_document or None,
            'service': v.service_history or None, 'noc': v.noc_document or None,
        },
    })

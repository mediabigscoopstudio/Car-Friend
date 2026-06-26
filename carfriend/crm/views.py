from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from accounts.models import User, DealerProfile
from vehicles.models import Vehicle
from crm.models import Lead, Bid, LeadNote
from crm.services import transition_lead
from auctions.models import OCBListing
from inspections.models import InspectionVisit
from inspections.assignment import assign_inspector_to_lead, inspectors_for_vehicle


def _internal_check(request):
    return (
        request.user.is_authenticated
        and (request.user.is_staff_role() or request.user.is_superuser)
    )


def _sales_or_admin(request):
    # Sales CRM (dealer network + deals) is for Sales Associates + Admin only.
    return request.user.is_authenticated and (
        request.user.role in [User.ROLE_SALES, User.ROLE_ADMIN] or request.user.is_superuser
    )


# ── Teams Dashboard ───────────────────────────────────────────────────────────

@login_required(login_url='/auth/login/')
def teams_dashboard(request):
    if not _internal_check(request):
        return redirect('/')
    # Sales Associates must never see the generic lead dashboard — send them to
    # their own OCB-centric dashboard (no leads / sellers).
    if request.user.is_sales:
        return redirect('/crm/sales/dashboard/')
    # Procurement Associates only handle handovers — send them to their dashboard.
    if request.user.is_procurement:
        return redirect('/crm/procurement/dashboard/')
    ctx = {
        'total_leads':   Lead.objects.count(),
        'new_leads':     Lead.objects.filter(stage=Lead.STAGE_NEW).count(),
        'in_inspection': Lead.objects.filter(stage=Lead.STAGE_INSP_SCHED).count(),
        'in_auction':    Lead.objects.filter(stage=Lead.STAGE_AUCTION).count(),
        'closed':        Lead.objects.filter(stage=Lead.STAGE_CLOSED).count(),
        'total_dealers': DealerProfile.objects.count(),
        'total_bids':    Bid.objects.count(),
        'recent_leads':  Lead.objects.select_related('vehicle', 'seller')[:5],
    }
    return render(request, 'teams/dashboard.html', ctx)


# ── Lead Pipeline ─────────────────────────────────────────────────────────────

@login_required(login_url='/auth/login/')
def pipeline(request):
    if not _internal_check(request):
        return redirect('/')
    if request.user.is_sales:            # Sales Associates have no lead access
        return redirect('/crm/sales/dashboard/')
    if request.user.is_procurement:      # Procurement has no lead access
        return redirect('/crm/procurement/dashboard/')

    # Full lead pipeline. Leads are not assigned to individual Retail Associates
    # in the current workflow (assigned_to is null or the Lead Manager), so an
    # assigned_to=request.user filter showed zero leads. Show all real leads.
    leads = Lead.objects.all().select_related('vehicle', 'seller')

    stages = {}
    for stage_val, stage_label in Lead.STAGE_CHOICES:
        stage_leads = [l for l in leads if l.stage == stage_val]
        stages[stage_val] = {
            'label': stage_label,
            'leads': stage_leads,
            'count': len(stage_leads),
        }

    return render(request, 'teams/pipeline.html', {
        'stages':        stages,
        'stage_choices': Lead.STAGE_CHOICES,
    })


@login_required(login_url='/auth/login/')
def lead_detail(request, lead_id):
    if not _internal_check(request):
        return redirect('/')
    lead = get_object_or_404(Lead, id=lead_id)
    inspectors = inspectors_for_vehicle(lead.vehicle)
    inspection_visit = getattr(lead, 'inspection_visit', None)
    bids = Bid.objects.filter(vehicle=lead.vehicle).order_by('-amount')[:10]

    # OCB(s) for this lead — linked via the vehicle (Lead.vehicle is OneToOne;
    # OCBListing has no direct lead FK).
    ocb_rows = []
    if lead.vehicle:
        ocbs = (OCBListing.objects.filter(vehicle=lead.vehicle)
                .select_related('sales_associate').prefetch_related('offers__dealer')
                .order_by('-created_at'))
        for o in ocbs:
            offers = list(o.offers.all())
            winner = next((of for of in offers if of.is_selected), None)
            ocb_rows.append({
                'ocb': o,
                'offers': len(offers),
                'sales': (o.sales_associate.get_full_name() or o.sales_associate.username)
                         if o.sales_associate else '—',
                'winner': winner,
            })
    # Allow creating another OCB only when none exist or all existing are closed/cancelled.
    can_create_more = (not ocb_rows) or all(
        r['ocb'].status in ('accepted', 'rejected') for r in ocb_rows)

    ctx = {
        'lead':             lead,
        'vehicle':          lead.vehicle,
        'seller':           lead.seller,
        'inspectors':       inspectors,
        'inspection_visit': inspection_visit,
        'bids':             bids,
        'stage_choices':    Lead.STAGE_CHOICES,
        'ocb_rows':         ocb_rows,
        'can_create_more':  can_create_more,
        'lead_notes':       lead.call_notes.select_related('author').all(),
    }
    return render(request, 'teams/lead_detail.html', ctx)


@login_required(login_url='/auth/login/')
def lead_add_note(request, lead_id):
    """Retail Associate logs a call note on a lead. POST only."""
    if request.method != 'POST':
        return redirect(f'/pipeline/{lead_id}/')
    if not (request.user.is_retail or request.user.is_superuser):
        return redirect('/')
    lead = get_object_or_404(Lead, id=lead_id)
    text = (request.POST.get('note') or '').strip()
    if text:
        LeadNote.objects.create(lead=lead, author=request.user, note=text)
        messages.success(request, 'Note added.')
    return redirect(f'/pipeline/{lead.id}/')


@login_required(login_url='/auth/login/')
def lead_move(request, lead_id):
    # The ONE manual override. Status is otherwise read-only and event-driven;
    # only an admin may force a stage, and it is audited via transition_lead.
    if request.method != 'POST':
        return redirect('pipeline')
    if not (request.user.role == User.ROLE_ADMIN or request.user.is_superuser):
        messages.error(request, 'Lead status is automatic — only an admin can override it.')
        return redirect('lead_detail', lead_id=lead_id)
    lead = get_object_or_404(Lead, id=lead_id)
    new_stage = request.POST.get('stage')
    if new_stage in dict(Lead.STAGE_CHOICES):
        transition_lead(lead, "manual_override", actor=request.user, to_stage=new_stage)
        messages.success(request, f'Lead moved to {lead.get_stage_display()}.')
    return redirect('lead_detail', lead_id=lead_id)


@login_required(login_url='/auth/login/')
def assign_inspector(request, lead_id):
    if not (request.user.role in [User.ROLE_RETAIL, User.ROLE_ADMIN] or request.user.is_superuser):
        return redirect('/')
    lead = get_object_or_404(Lead, id=lead_id)

    if request.method == 'POST':
        inspector_id = request.POST.get('inspector_id', '').strip()
        scheduled_at = request.POST.get('scheduled_at', '').strip()
        address      = request.POST.get('inspection_address', '').strip() or lead.vehicle.inspection_address

        if not inspector_id:
            messages.error(request, 'Please select an inspector.')
            return redirect('lead_detail', lead_id=lead_id)
        if not scheduled_at:
            messages.error(request, 'Please pick a date and time.')
            return redirect('lead_detail', lead_id=lead_id)

        inspector = get_object_or_404(User, id=inspector_id, role=User.ROLE_INSPECTOR)

        _, previous = assign_inspector_to_lead(
            lead, inspector, scheduled_at=scheduled_at, address=address,
            actor=request.user, request=request)

        name = inspector.get_full_name() or inspector.email
        if previous and previous.id != inspector.id:
            messages.success(request, f'Inspection reassigned to {name}.')
        else:
            messages.success(request, f'Inspector {name} assigned. Inspection scheduled.')
        return redirect('lead_detail', lead_id=lead_id)

    return redirect('lead_detail', lead_id=lead_id)


# ── Sellers ───────────────────────────────────────────────────────────────────

@login_required(login_url='/auth/login/')
def sellers(request):
    if not _internal_check(request):
        return redirect('/')
    if request.user.is_sales:            # Sales Associates have no seller access
        return redirect('/crm/sales/dashboard/')
    if request.user.is_procurement:      # Procurement has no seller access
        return redirect('/crm/procurement/dashboard/')
    all_sellers = User.objects.filter(role=User.ROLE_SELLER).prefetch_related('vehicles', 'leads')
    return render(request, 'teams/sellers.html', {'sellers': all_sellers})


# ── Dealer Network ────────────────────────────────────────────────────────────

@login_required(login_url='/auth/login/')
def dealers(request):
    if not _sales_or_admin(request):
        return redirect('/')
    all_dealers = DealerProfile.objects.select_related('user').order_by('-created_at')
    return render(request, 'teams/dealers.html', {'dealers': all_dealers})


@login_required(login_url='/auth/login/')
def dealer_detail(request, dealer_id):
    if not _sales_or_admin(request):
        return redirect('/')
    dealer = get_object_or_404(DealerProfile, id=dealer_id)
    bids = Bid.objects.filter(dealer=dealer.user).select_related('vehicle').order_by('-created_at')
    return render(request, 'teams/dealer_detail.html', {'dealer': dealer, 'bids': bids})


# ── Deals ─────────────────────────────────────────────────────────────────────

@login_required(login_url='/auth/login/')
def deals(request):
    if not _sales_or_admin(request):
        return redirect('/')
    vehicles_in_play = Vehicle.objects.filter(
        status__in=[Vehicle.STATUS_AUCTION, Vehicle.STATUS_APPROVED, Vehicle.STATUS_INSPECTED]
    ).prefetch_related('bids__dealer')
    return render(request, 'teams/deals.html', {'vehicles': vehicles_in_play})


@login_required(login_url='/auth/login/')
def deal_detail(request, vehicle_id):
    if not _sales_or_admin(request):
        return redirect('/')
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)
    bids = Bid.objects.filter(vehicle=vehicle).select_related('dealer').order_by('-amount')
    return render(request, 'teams/deal_detail.html', {
        'vehicle': vehicle,
        'bids':    bids,
        'winning': bids.first(),
        'lead':    getattr(vehicle, 'lead', None),
    })


# ── Inspector dashboard (teams) ───────────────────────────────────────────────

@login_required(login_url='/auth/login/')
def inspector_dashboard(request):
    if request.user.role not in [User.ROLE_INSPECTOR, User.ROLE_ADMIN] and not request.user.is_superuser:
        return redirect('/')
    visits = InspectionVisit.objects.filter(
        inspector=request.user
    ).select_related('vehicle', 'lead').order_by('scheduled_at')

    pending = [v for v in visits if v.status == InspectionVisit.Status.SCHEDULED]
    done    = [v for v in visits if v.status in [InspectionVisit.Status.SUBMITTED, InspectionVisit.Status.APPROVED]]

    return render(request, 'teams/inspector_dashboard.html', {
        'pending': pending,
        'done':    done,
    })


# ── Lead Manager: dedicated dashboard + inspection calendar ───────────────────

_INSPECTOR_PALETTE = ["#2D6CDF", "#0FB5C9", "#FF6A5A", "#5AA9E6",
                      "#7C4DFF", "#E8A33D", "#1B9E77", "#C2185B"]


def _inspector_colour(inspector_id):
    if not inspector_id:
        return "#8595AB"
    return _INSPECTOR_PALETTE[inspector_id % len(_INSPECTOR_PALETTE)]


def _require_lead_manager(request):
    """Return a redirect response if the user isn't a Lead Manager, else None.
    Not authenticated -> teams login; wrong role -> their own dashboard."""
    if not request.user.is_authenticated:
        return redirect('/auth/login/')
    if request.user.role != User.ROLE_LEAD_MANAGER and not request.user.is_superuser:
        from accounts.views import get_dashboard_url
        return redirect(get_dashboard_url(request.user))
    return None


def lead_manager_dashboard(request):
    guard = _require_lead_manager(request)
    if guard:
        return guard
    today = timezone.localdate()
    ctx = {
        'total_leads':           Lead.objects.count(),
        'new_leads':             Lead.objects.filter(stage='new').count(),
        'inspections_scheduled': Lead.objects.filter(stage='inspection_scheduled').count(),
        'qualified_today':       Lead.objects.filter(stage='qualified', updated_at__date=today).count(),
        'recent_leads':          Lead.objects.filter(stage__in=['new', 'qualified'])
                                     .select_related('vehicle', 'seller').order_by('-created_at')[:10],
    }
    return render(request, 'teams/lead_manager/dashboard.html', ctx)


def lead_manager_calendar(request):
    guard = _require_lead_manager(request)
    if guard:
        return guard
    inspectors = User.objects.filter(role=User.ROLE_INSPECTOR, is_suspended=False).order_by('username')
    legend = [{'name': (i.get_full_name() or i.username), 'colour': _inspector_colour(i.id)}
              for i in inspectors]
    return render(request, 'teams/lead_manager/inspection_calendar.html', {'legend': legend})


def inspection_visits_json(request):
    guard = _require_lead_manager(request)
    if guard:
        return guard
    qs = InspectionVisit.objects.select_related('vehicle', 'inspector', 'lead__seller')
    start, end = request.GET.get('start'), request.GET.get('end')
    if start and parse_datetime(start):
        qs = qs.filter(scheduled_at__gte=parse_datetime(start))
    if end and parse_datetime(end):
        qs = qs.filter(scheduled_at__lte=parse_datetime(end))

    events = []
    for v in qs:
        veh = v.vehicle
        car = ''
        if veh:
            car = f"{veh.make} {veh.model} {veh.year}".strip()
            if getattr(veh, 'plate_number', ''):
                car += f" ({veh.plate_number})"
        seller = ''
        lead = getattr(v, 'lead', None)
        if lead and getattr(lead, 'seller', None):
            seller = lead.seller.get_full_name() or lead.seller.username
        elif veh and getattr(veh, 'seller', None):
            seller = veh.seller.get_full_name() or veh.seller.username
        insp = v.inspector
        inspector_name = (insp.get_full_name() or insp.username) if insp else 'Unassigned'
        start_at = getattr(v, 'scheduled_at', None)
        events.append({
            'id': v.id,
            'title': (f"{car} — {seller}".strip(' —') or 'Inspection'),
            'start': start_at.isoformat() if start_at else None,
            'end': (start_at + timedelta(hours=1)).isoformat() if start_at else None,
            'color': _inspector_colour(v.inspector_id),
            'extendedProps': {
                'inspector': inspector_name,
                'car': car or '—',
                'seller': seller or '—',
                'address': getattr(v, 'inspection_address', '') or '—',
                'status': v.get_status_display(),
            },
        })
    return JsonResponse(events, safe=False)

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from accounts.models import User, DealerProfile
from vehicles.models import Vehicle
from crm.models import Lead, Bid
from inspections.models import InspectionVisit


def _internal_check(request):
    return (
        request.user.is_authenticated
        and (request.user.is_staff_role() or request.user.is_superuser)
    )


# ── Teams Dashboard ───────────────────────────────────────────────────────────

@login_required(login_url='/auth/login/')
def teams_dashboard(request):
    if not _internal_check(request):
        return redirect('/')
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

    if request.user.role == User.ROLE_RETAIL:
        leads = Lead.objects.filter(assigned_to=request.user).select_related('vehicle', 'seller')
    else:
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
    inspectors = User.objects.filter(role=User.ROLE_INSPECTOR, is_active=True)
    inspection_visit = getattr(lead, 'inspection_visit', None)
    bids = Bid.objects.filter(vehicle=lead.vehicle).order_by('-amount')[:10]
    ctx = {
        'lead':             lead,
        'vehicle':          lead.vehicle,
        'seller':           lead.seller,
        'inspectors':       inspectors,
        'inspection_visit': inspection_visit,
        'bids':             bids,
        'stage_choices':    Lead.STAGE_CHOICES,
    }
    return render(request, 'teams/lead_detail.html', ctx)


@login_required(login_url='/auth/login/')
def lead_move(request, lead_id):
    if request.method != 'POST':
        return redirect('pipeline')
    lead = get_object_or_404(Lead, id=lead_id)
    new_stage = request.POST.get('stage')
    valid_stages = [s[0] for s in Lead.STAGE_CHOICES]
    if new_stage in valid_stages:
        lead.stage = new_stage
        lead.save()
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

        visit, created = InspectionVisit.objects.get_or_create(
            lead=lead,
            defaults={
                'vehicle':            lead.vehicle,
                'inspector':          inspector,
                'assigned_by':        request.user,
                'scheduled_at':       scheduled_at,
                'inspection_address': address,
                'status':             InspectionVisit.Status.SCHEDULED,
            }
        )
        if not created:
            visit.inspector          = inspector
            visit.assigned_by        = request.user
            visit.scheduled_at       = scheduled_at
            visit.inspection_address = address
            visit.status             = InspectionVisit.Status.SCHEDULED
            visit.save()

        lead.stage = Lead.STAGE_INSP_SCHED
        lead.save()
        lead.vehicle.status             = Vehicle.STATUS_INSPECTION
        lead.vehicle.inspection_address = address
        lead.vehicle.save()

        name = inspector.get_full_name() or inspector.email
        messages.success(request, f'Inspector {name} assigned. Inspection scheduled.')
        return redirect('lead_detail', lead_id=lead_id)

    return redirect('lead_detail', lead_id=lead_id)


# ── Sellers ───────────────────────────────────────────────────────────────────

@login_required(login_url='/auth/login/')
def sellers(request):
    if not _internal_check(request):
        return redirect('/')
    all_sellers = User.objects.filter(role=User.ROLE_SELLER).prefetch_related('vehicles', 'leads')
    return render(request, 'teams/sellers.html', {'sellers': all_sellers})


# ── Dealer Network ────────────────────────────────────────────────────────────

@login_required(login_url='/auth/login/')
def dealers(request):
    if not _internal_check(request):
        return redirect('/')
    all_dealers = DealerProfile.objects.select_related('user').order_by('-created_at')
    return render(request, 'teams/dealers.html', {'dealers': all_dealers})


@login_required(login_url='/auth/login/')
def dealer_detail(request, dealer_id):
    if not _internal_check(request):
        return redirect('/')
    dealer = get_object_or_404(DealerProfile, id=dealer_id)
    bids = Bid.objects.filter(dealer=dealer.user).select_related('vehicle').order_by('-created_at')
    return render(request, 'teams/dealer_detail.html', {'dealer': dealer, 'bids': bids})


# ── Deals ─────────────────────────────────────────────────────────────────────

@login_required(login_url='/auth/login/')
def deals(request):
    if not _internal_check(request):
        return redirect('/')
    vehicles_in_play = Vehicle.objects.filter(
        status__in=[Vehicle.STATUS_AUCTION, Vehicle.STATUS_APPROVED, Vehicle.STATUS_INSPECTED]
    ).prefetch_related('bids__dealer')
    return render(request, 'teams/deals.html', {'vehicles': vehicles_in_play})


@login_required(login_url='/auth/login/')
def deal_detail(request, vehicle_id):
    if not _internal_check(request):
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

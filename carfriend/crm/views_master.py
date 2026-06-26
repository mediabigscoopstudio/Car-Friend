from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from accounts.decorators import admin_required, role_required, inspector_required
from accounts.models import User, DealerProfile
from vehicles.models import Vehicle
from crm.models import Lead, Bid, LeadNote
from crm.services import transition_lead
from auctions.models import OCBListing
from inspections.assignment import assign_inspector_to_lead, inspectors_for_vehicle
from inspections.models import InspectionVisit

retail_or_admin    = role_required('retail', 'admin')
sales_or_admin     = role_required('sales', 'admin')
inspector_or_admin = role_required('inspector', 'admin')


@retail_or_admin
def master_pipeline(request):
    leads = Lead.objects.all().select_related('vehicle', 'seller', 'assigned_to')
    stages = {}
    for stage_val, stage_label in Lead.STAGE_CHOICES:
        stage_leads = [l for l in leads if l.stage == stage_val]
        stages[stage_val] = {'label': stage_label, 'leads': stage_leads, 'count': len(stage_leads)}
    return render(request, 'master/pipeline.html', {
        'active':       'pipeline',
        'stages':       stages,
        'stage_choices': Lead.STAGE_CHOICES,
        'total':        leads.count(),
    })


@retail_or_admin
def master_lead_detail(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    inspectors       = inspectors_for_vehicle(lead.vehicle)
    inspection_visit = getattr(lead, 'inspection_visit', None)
    bids             = Bid.objects.filter(vehicle=lead.vehicle).order_by('-amount')[:10]
    # OCB oversight (read-only): any OCB on this lead's vehicle, with offers + chat.
    ocbs = []
    if lead.vehicle_id:
        ocbs = (OCBListing.objects
                .filter(vehicle=lead.vehicle)
                .select_related('assigned_to', 'sales_associate')
                .prefetch_related('offers__dealer', 'offers__submitted_by', 'messages__sender')
                .order_by('-created_at'))
    return render(request, 'master/lead_detail.html', {
        'active':           'pipeline',
        'lead':             lead,
        'vehicle':          lead.vehicle,
        'seller':           lead.seller,
        'inspectors':       inspectors,
        'inspection_visit': inspection_visit,
        'bids':             bids,
        'stage_choices':    Lead.STAGE_CHOICES,
        'lead_notes':       lead.call_notes.select_related('author').all(),
        'ocbs':             ocbs,
    })


@retail_or_admin
def master_lead_add_note(request, lead_id):
    """Admin logs a call note on a lead — reuses the LeadNote model (same as the
    Retail Associate page). POST only."""
    if request.method != 'POST':
        return redirect('master_lead_detail', lead_id=lead_id)
    lead = get_object_or_404(Lead, id=lead_id)
    text = (request.POST.get('note') or '').strip()
    if text:
        LeadNote.objects.create(lead=lead, author=request.user, note=text)
        messages.success(request, 'Note added.')
    return redirect('master_lead_detail', lead_id=lead_id)


@retail_or_admin
def master_lead_move(request, lead_id):
    # The ONE manual override. Status is otherwise read-only and event-driven;
    # only an admin may force a stage, and it is audited via transition_lead.
    if request.method != 'POST':
        return redirect('master_pipeline')
    if not (request.user.role == User.ROLE_ADMIN or request.user.is_superuser):
        messages.error(request, 'Lead status is automatic — only an admin can override it.')
        return redirect('master_lead_detail', lead_id=lead_id)
    lead = get_object_or_404(Lead, id=lead_id)
    new_stage = request.POST.get('stage')
    if new_stage in dict(Lead.STAGE_CHOICES):
        transition_lead(lead, "manual_override", actor=request.user, to_stage=new_stage)
        messages.success(request, f'Lead moved to {lead.get_stage_display()}.')
    return redirect('master_lead_detail', lead_id=lead_id)


@retail_or_admin
def master_assign_inspector(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    if request.method == 'POST':
        inspector_id = request.POST.get('inspector_id', '').strip()
        scheduled_at = request.POST.get('scheduled_at', '').strip()
        address      = request.POST.get('inspection_address', '').strip() or lead.vehicle.inspection_address

        if not inspector_id:
            messages.error(request, 'Please select an inspector.')
            return redirect('master_lead_detail', lead_id=lead_id)
        if not scheduled_at:
            messages.error(request, 'Please pick a date and time.')
            return redirect('master_lead_detail', lead_id=lead_id)

        inspector = get_object_or_404(User, id=inspector_id, role=User.ROLE_INSPECTOR)

        # Single atomic path: visit (create/relink) + state transition + audit.
        assign_inspector_to_lead(lead, inspector, scheduled_at=scheduled_at,
                                 address=address, actor=request.user, request=request)

        name = inspector.get_full_name() or inspector.email
        messages.success(request, f'Inspector {name} assigned and inspection scheduled.')
    return redirect('master_lead_detail', lead_id=lead_id)


@retail_or_admin
def master_sellers(request):
    all_sellers = User.objects.filter(role=User.ROLE_SELLER).prefetch_related('vehicles', 'leads')
    return render(request, 'master/sellers.html', {
        'active':  'sellers',
        'sellers': all_sellers,
    })


@sales_or_admin
def master_dealers(request):
    all_dealers = DealerProfile.objects.select_related('user').order_by('-created_at')
    return render(request, 'master/dealers.html', {
        'active':  'dealers',
        'dealers': all_dealers,
    })


@sales_or_admin
def master_dealer_detail(request, dealer_id):
    dealer = get_object_or_404(DealerProfile, id=dealer_id)
    bids = Bid.objects.filter(dealer=dealer.user).select_related('vehicle').order_by('-created_at')
    return render(request, 'master/dealer_detail.html', {
        'active': 'dealers',
        'dealer': dealer,
        'bids':   bids,
    })


@sales_or_admin
def master_deals(request):
    vehicles_in_play = Vehicle.objects.filter(
        status__in=[Vehicle.STATUS_AUCTION, Vehicle.STATUS_APPROVED, Vehicle.STATUS_INSPECTED]
    ).prefetch_related('bids__dealer')
    return render(request, 'master/deals.html', {
        'active':   'deals',
        'vehicles': vehicles_in_play,
    })


@sales_or_admin
def master_deal_detail(request, vehicle_id):
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)
    bids    = Bid.objects.filter(vehicle=vehicle).select_related('dealer').order_by('-amount')
    return render(request, 'master/deal_detail.html', {
        'active':  'deals',
        'vehicle': vehicle,
        'bids':    bids,
        'winning': bids.first(),
    })


# ── Inspector overview (master) ───────────────────────────────────────────────

@inspector_or_admin
def master_inspector_dashboard(request):
    if request.user.role == 'admin' or request.user.is_superuser:
        visits = InspectionVisit.objects.all().select_related('vehicle', 'lead', 'inspector')
    else:
        visits = InspectionVisit.objects.filter(
            inspector=request.user
        ).select_related('vehicle', 'lead')

    pending = [v for v in visits if v.status == InspectionVisit.Status.SCHEDULED]
    done    = [v for v in visits if v.status in [InspectionVisit.Status.SUBMITTED, InspectionVisit.Status.APPROVED]]

    return render(request, 'master/inspector_dashboard.html', {
        'active':  'inspector',
        'pending': pending,
        'done':    done,
    })

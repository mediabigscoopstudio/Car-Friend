from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from accounts.decorators import admin_required, role_required, inspector_required
from accounts.models import User, DealerProfile
from vehicles.models import Vehicle
from crm.models import Lead, InspectionJob, Bid

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
        'active': 'pipeline',
        'stages': stages,
        'stage_choices': Lead.STAGE_CHOICES,
        'total': leads.count(),
    })


@retail_or_admin
def master_lead_detail(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    inspectors = User.objects.filter(role=User.ROLE_INSPECTOR, is_active=True)
    inspection_job = getattr(lead, 'inspection_job', None)
    bids = Bid.objects.filter(vehicle=lead.vehicle).order_by('-amount')[:10]
    return render(request, 'master/lead_detail.html', {
        'active':         'pipeline',
        'lead':           lead,
        'vehicle':        lead.vehicle,
        'seller':         lead.seller,
        'inspectors':     inspectors,
        'inspection_job': inspection_job,
        'bids':           bids,
        'stage_choices':  Lead.STAGE_CHOICES,
    })


@retail_or_admin
def master_lead_move(request, lead_id):
    if request.method != 'POST':
        return redirect('master_pipeline')
    lead = get_object_or_404(Lead, id=lead_id)
    new_stage = request.POST.get('stage')
    valid = [s[0] for s in Lead.STAGE_CHOICES]
    if new_stage in valid:
        lead.stage = new_stage
        lead.save()
        messages.success(request, f'Lead moved to {lead.get_stage_display()}.')
    return redirect('master_lead_detail', lead_id=lead_id)


@retail_or_admin
def master_assign_inspector(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    if request.method == 'POST':
        inspector_id = request.POST.get('inspector_id', '').strip()
        scheduled_at = request.POST.get('scheduled_at', '').strip()
        address      = request.POST.get('inspection_address', lead.vehicle.inspection_address).strip()

        if not inspector_id:
            messages.error(request, 'Please select an inspector.')
            return redirect('master_lead_detail', lead_id=lead_id)
        if not scheduled_at:
            messages.error(request, 'Please pick a date and time.')
            return redirect('master_lead_detail', lead_id=lead_id)

        inspector = get_object_or_404(User, id=inspector_id, role=User.ROLE_INSPECTOR)
        job, created = InspectionJob.objects.get_or_create(
            lead=lead,
            defaults={
                'vehicle':            lead.vehicle,
                'inspector':          inspector,
                'assigned_by':        request.user,
                'scheduled_at':       scheduled_at,
                'inspection_address': address,
                'status':             InspectionJob.STATUS_SCHEDULED,
            }
        )
        if not created:
            job.inspector          = inspector
            job.scheduled_at       = scheduled_at
            job.inspection_address = address
            job.status             = InspectionJob.STATUS_SCHEDULED
            job.save()

        lead.stage          = Lead.STAGE_INSP_SCHED
        lead.save()
        lead.vehicle.status = Vehicle.STATUS_INSPECTION
        lead.vehicle.save()

        name = inspector.get_full_name() or inspector.email
        messages.success(request, f'Inspector {name} assigned and inspection scheduled.')
    return redirect('master_lead_detail', lead_id=lead_id)


@retail_or_admin
def master_sellers(request):
    all_sellers = User.objects.filter(role=User.ROLE_SELLER).prefetch_related('vehicles', 'leads')
    return render(request, 'master/sellers.html', {
        'active':   'sellers',
        'sellers':  all_sellers,
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


# ── Inspector (master host) ───────────────────────────────────────────────────

@inspector_or_admin
def master_inspector_dashboard(request):
    if request.user.role == 'admin' or request.user.is_superuser:
        jobs = InspectionJob.objects.all().select_related('vehicle', 'lead', 'inspector')
    else:
        jobs = InspectionJob.objects.filter(
            inspector=request.user
        ).select_related('vehicle', 'lead')

    pending = [j for j in jobs if j.status == InspectionJob.STATUS_SCHEDULED]
    done    = [j for j in jobs if j.status in [InspectionJob.STATUS_SUBMITTED, InspectionJob.STATUS_APPROVED]]

    return render(request, 'master/inspector_dashboard.html', {
        'active':   'inspector',
        'pending':  pending,
        'done':     done,
    })


@inspector_or_admin
def master_inspector_job(request, job_id):
    job = get_object_or_404(InspectionJob, id=job_id)
    if request.user.role == 'inspector' and job.inspector_id != request.user.id:
        return redirect('master_inspector_dashboard')
    return render(request, 'master/inspector_job.html', {
        'active': 'inspector',
        'job':    job,
    })


@inspector_or_admin
def master_submit_report(request, job_id):
    job = get_object_or_404(InspectionJob, id=job_id)
    if request.user.role == 'inspector' and job.inspector_id != request.user.id:
        return redirect('master_inspector_dashboard')

    if request.method == 'POST':
        job.exterior_score  = int(request.POST.get('exterior_score', 0))
        job.interior_score  = int(request.POST.get('interior_score', 0))
        job.engine_score    = int(request.POST.get('engine_score', 0))
        job.tyres_score     = int(request.POST.get('tyres_score', 0))
        job.overall_score   = int(request.POST.get('overall_score', 0))
        job.condition_grade = job.compute_grade()
        job.inspector_notes = request.POST.get('inspector_notes', '')
        job.status          = InspectionJob.STATUS_SUBMITTED

        if request.FILES.get('report_pdf'):
            job.report_pdf = request.FILES['report_pdf']

        job.save()

        job.vehicle.status                  = Vehicle.STATUS_INSPECTED
        job.vehicle.inspection_report_ready = True
        job.vehicle.save()

        try:
            job.lead.stage = Lead.STAGE_INSP_DONE
            job.lead.save()
        except Exception:
            pass

        messages.success(request, 'Inspection report submitted successfully.')
        return redirect('master_inspector_dashboard')

    return redirect('master_inspector_job', job_id=job_id)

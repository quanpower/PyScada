# -*- coding: utf-8 -*-
from pyscada import version as core_version
from pyscada.models import Variable
from pyscada.models import RecordedData
from pyscada.models import RecordedEvent
from pyscada.hmi.models import Chart
from pyscada.hmi.models import Page
from pyscada.hmi.models import ControlItem
from pyscada.hmi.models import SlidingPanelMenu
from pyscada.hmi.models import CustomHTMLPanel
from pyscada.hmi.models import GroupDisplayPermission
from pyscada.hmi.models import Widget
from pyscada.hmi.models import View

from pyscada.models import Log
from pyscada.models import DeviceWriteTask

from pyscada import log
#from pyscada.export import timestamp_unix_to_matlab
from django.shortcuts import render
from django.http import HttpResponse
from django.core import serializers
from django.core.management import call_command
from django.utils import timezone
from django.template.loader import get_template
from django.template.response import TemplateResponse
from django.db import connection
from django.shortcuts import redirect
from django.contrib.auth import logout
from django.contrib.auth.models import User
from django.views.decorators.csrf import requires_csrf_token
import time
import json


def index(request):
	if not request.user.is_authenticated():
		return redirect('/accounts/login/?next=%s' % request.path)
	if GroupDisplayPermission.objects.count() == 0:
		view_list = View.objects.all()
	else:
		view_list = View.objects.filter(groupdisplaypermission__hmi_group__in=request.user.groups.iterator()).distinct()
	c = {
		'user': request.user,
		'view_list':view_list,
		'version_string':core_version
	}
	return TemplateResponse(request, 'view_overview.html', c) # HttpResponse(t.render(c))

@requires_csrf_token
def view(request,link_title):
	if not request.user.is_authenticated():
		return redirect('/accounts/login/?next=%s' % request.path)

	page_template = get_template('content_page.html')
	widget_row_template = get_template('widget_row.html')

	try:
		view = View.objects.get(link_title=link_title)
	except:
		return HttpResponse(status=404)
	if GroupDisplayPermission.objects.count() == 0:
		# no groups
		page_list = view.pages.all()
		sliding_panel_list = view.sliding_panel_menus.all()
	
		visible_widget_list = Widget.objects.filter(page__in=page_list.iterator()).values_list('pk',flat=True)
		visible_custom_html_panel_list = CustomHTMLPanel.objects.all().values_list('pk',flat=True)
		visible_chart_list = Chart.objects.all().values_list('pk',flat=True)
		visible_control_element_list = ControlItem.objects.all().values_list('pk',flat=True)
	else:
		page_list = view.pages.filter(groupdisplaypermission__hmi_group__in=request.user.groups.iterator()).distinct()
	
		sliding_panel_list = view.sliding_panel_menus.filter(groupdisplaypermission__hmi_group__in=request.user.groups.iterator()).distinct()
	
		visible_widget_list = Widget.objects.filter(groupdisplaypermission__hmi_group__in=request.user.groups.iterator(),page__in=page_list.iterator()).values_list('pk',flat=True)
		visible_custom_html_panel_list = CustomHTMLPanel.objects.filter(groupdisplaypermission__hmi_group__in=request.user.groups.iterator()).values_list('pk',flat=True)
		visible_chart_list = Chart.objects.filter(groupdisplaypermission__hmi_group__in=request.user.groups.iterator()).values_list('pk',flat=True)
	
		visible_control_element_list = GroupDisplayPermission.objects.filter(hmi_group__in=request.user.groups.iterator()).values_list('control_items',flat=True)

	panel_list   = sliding_panel_list.filter(position__in=(1,2,))
	control_list = sliding_panel_list.filter(position=0)

	current_row = 0
	has_chart = False
	widgets = []
	widget_rows_html = ""
	pages_html = ""
	for page in page_list:
		current_row = 0
		has_chart = False
		widgets = []
		widget_rows_html = ""
		for widget in page.widget_set.all():
			# check if row has changed
			if current_row != widget.row:
				# render new widget row and reset all loop variables
				widget_rows_html += widget_row_template.render({'row':current_row,'has_chart':has_chart,'widgets':widgets,'visible_control_element_list':visible_control_element_list},request)
				current_row = widget.row
				has_chart = False
				widgets = []
			if not widget.pk in visible_widget_list:
				continue
			if not widget.visable:
				continue
			if widget.chart:
				if not widget.chart.visable():
					continue
				if not widget.chart.pk in visible_chart_list:
					continue
				has_chart = True
				widgets.append(widget)
			elif widget.control_panel:
				widgets.append(widget)
			elif widget.process_flow_diagram:
				widgets.append(widget)
			elif widget.custom_html_panel:
				if not widget.custom_html_panel.pk in visible_custom_html_panel_list:
					continue
				widgets.append(widget)
		widget_rows_html += widget_row_template.render({'row':current_row,'has_chart':has_chart,'widgets':widgets,'visible_control_element_list':visible_control_element_list},request)
		pages_html += page_template.render({'page':page,'widget_rows_html':widget_rows_html},request)

	c = {
		'page_list': page_list,
		'pages_html':pages_html,
		'panel_list': panel_list,
		'control_list':control_list,
		'user': request.user,
		'visible_control_element_list':visible_control_element_list,
		'view_title':view.title,
		'version_string':core_version
	}

	log.webnotice('open hmi',request.user)
	return TemplateResponse(request, 'view.html', c)

def log_data(request):
	if not request.user.is_authenticated():
		return redirect('/accounts/login/?next=%s' % request.path)
	if request.POST.has_key('timestamp'):
		timestamp = float(request.POST['timestamp'])
	else:
		timestamp = (time.time()-(300))*1000 # get log of last 5 minutes

	data = Log.objects.filter(level__gte=6,id__gt=int(int(timestamp)*2097152)+2097151).order_by('-timestamp')
	odata = []
	for item in data:
		odata.append({"timestamp":item.timestamp*1000,"level":item.level,"message":item.message,"username":item.user.username if item.user else "None"})
	jdata = json.dumps(odata,indent=2)

	return HttpResponse(jdata, content_type='application/json')

def form_log_entry(request):
	if not request.user.is_authenticated():
		return redirect('/accounts/login/?next=%s' % request.path)
	if request.POST.has_key('message') and request.POST.has_key('level'):
		log.add(request.POST['message'],request.POST['level'],request.user)
		return HttpResponse(status=200)
	else:
		return HttpResponse(status=404)

def	form_write_task(request):
	if not request.user.is_authenticated():
		return redirect('/accounts/login/?next=%s' % request.path)
	if request.POST.has_key('var_id') and request.POST.has_key('value'):
		cwt = DeviceWriteTask(variable_id = request.POST['var_id'],value=request.POST['value'],start=time.time(),user=request.user)
		cwt.save()
		return HttpResponse(status=200)
	else:
		return HttpResponse(status=404)

def get_cache_data(request):
	if not request.user.is_authenticated():
		return redirect('/accounts/login/?next=%s' % request.path)

		
	if request.POST.has_key('init'):
		init = bool(float(request.POST['init']))
	else:
		init = False

	if request.POST.has_key('variables[]'):
		active_variables = request.POST.getlist('variables[]')
	else:
		active_variables = list(GroupDisplayPermission.objects.filter(hmi_group__in=request.user.groups.iterator()).values_list('charts__variables',flat=True))
		active_variables += list(GroupDisplayPermission.objects.filter(hmi_group__in=request.user.groups.iterator()).values_list('control_items__variable',flat=True))
		active_variables += list(GroupDisplayPermission.objects.filter(hmi_group__in=request.user.groups.iterator()).values_list('custom_html_panels__variables',flat=True))
		active_variables = list(set(active_variables))
	
	timestamp = time.time()
	if request.POST.has_key('timestamp'):
		# query data from future is not supported
		if float(request.POST['timestamp']) >= timestamp-120*60:
			timestamp = min(float(request.POST['timestamp'])/1000.0,timestamp) 
	
	if init:
		first_timestamp = timestamp - 120*60
		last_timestamp  = timestamp
	else:
		first_timestamp = timestamp
		last_timestamp  = time.time()
	data = {}
	data = RecordedData.objects.get_values_in_time_range(\
		time_min = first_timestamp,\
		time_max = last_timestamp,\
		query_first_value = init,\
		time_in_ms = True,\
		key_is_variable_name = True,\
		add_timetamp_field = True,\
		add_fake_data = True,\
		variable_id__in = active_variables)
	if data is None:
		jdata = json.dumps({'server_time':time.time()*1000})
		return HttpResponse(jdata, content_type='application/json')
	#data["timestamp"] = time.time()*1000 # TODO max_time from data
	data["server_time"] = time.time()*1000
	jdata = json.dumps(data)
	return HttpResponse(jdata, content_type='application/json')

def logout_view(request):
	log.webnotice('logout',request.user)
	logout(request)
	# Redirect to a success page.
	return redirect('/accounts/login/?next=/')

def user_profile_change(request):
	return redirect('/accounts/login/?next=/')

#!/usr/bin/python
# -*- coding: utf-8 -*-
from pyscada import log
from pyscada.models import BackgroundTask
from pyscada.export.export import export_recordeddata_to_file
from pyscada.export.models import ScheduledExportTask, ExportTask


from django.conf import settings

from time import time, gmtime,strftime, mktime
from datetime import date,datetime, timedelta
from pytz import UTC

from threading import Timer
import os, sys

def _export_handler(job,today):
    
    if job.file_format.upper() == 'HDF5':
        file_ext    = '.h5'
    elif job.file_format.upper() == 'MAT':
        file_ext    = '.mat'
    elif job.file_format.upper() == 'CSV_EXCEL':
        file_ext    = '.csv'
    
    task_identifier=today.strftime('%Y%m%d')+'-%d'%job.pk
    bt = BackgroundTask(start=time(),\
        label='pyscada.export.export_measurement_data_%s'%task_identifier,\
        message='time waiting...',\
        timestamp=time(),\
        pid=str(os.getpid()),\
        identifier = task_identifier)
    bt.save()
    
    job.busy = True
    job.backgroundtask = bt
    job.save()

    
    export_recordeddata_to_file(\
        job.time_min(),\
        job.time_max(),\
        filename=None,\
        active_vars=job.variables.values_list('pk',flat=True),\
        file_extension = file_ext,\
        filename_suffix=job.filename_suffix,\
        backgroundtask_id=bt.pk,\
        export_task_id = job.pk,\
        mean_value_period = job.mean_value_period
        )
    job = ExportTask.objects.get(pk=job.pk)
    job.done     = True
    job.busy     = False
    job.datetime_fineshed = datetime.now(UTC)
    job.save()

    
class Handler:
    def __init__(self):
        '''
        
        '''
        self.dt_set = 5 # default value is every 5 seconds
        self._currend_day = gmtime().tm_yday
        
    def run(self):
        """
        this function will be called every self.dt_set seconds
            
        request data
            
        tm_wday 0=Monday 
        tm_yday   
        """
        today       = date.today()
        # only start new jobs after change the day changed
        if self._currend_day != gmtime().tm_yday:
            self._currend_day = gmtime().tm_yday
            for job in ScheduledExportTask.objects.filter(active=1): # get all active jobs
                
                add_task = False
                if job.export_period == 1: # daily
                    start_time      = '%s %02d:00:00'%((today - timedelta(1)).strftime('%d-%b-%Y'),job.day_time) # "%d-%b-%Y %H:%M:%S"
                    start_time      = mktime(datetime.strptime(start_time, "%d-%b-%Y %H:%M:%S").timetuple())
                    filename_suffix = 'daily_export_%d_%s'%(job.pk,job.label)
                    add_task = True
                elif job.export_period == 2 and time.gmtime().tm_yday%2 == 0: # on even days (2,4,...)
                    start_time      = '%s %02d:00:00'%((today - timedelta(2)).strftime('%d-%b-%Y'),job.day_time) # "%d-%b-%Y %H:%M:%S"
                    start_time      = mktime(datetime.strptime(start_time, "%d-%b-%Y %H:%M:%S").timetuple())
                    filename_suffix = 'two_day_export_%d_%s'%(job.pk,job.label)
                    add_task = True
                elif job.export_period == 7 and time.gmtime().tm_wday == 0: # on every monday
                    start_time      = '%s %02d:00:00'%((today - timedelta(7)).strftime('%d-%b-%Y'),job.day_time) # "%d-%b-%Y %H:%M:%S"
                    start_time      = mktime(datetime.strptime(start_time, "%d-%b-%Y %H:%M:%S").timetuple())
                    filename_suffix = 'weekly_export_%d_%s'%(job.pk,job.label)
                    add_task = True
                elif job.export_period == 14 and time.gmtime().tm_yday%14 == 0: # on every second monday
                    start_time      = '%s %02d:00:00'%((today - timedelta(14)).strftime('%d-%b-%Y'),job.day_time) # "%d-%b-%Y %H:%M:%S"
                    start_time      = mktime(datetime.strptime(start_time, "%d-%b-%Y %H:%M:%S").timetuple())
                    filename_suffix ='two_week_export_%d_%s'%(job.pk,job.label) 
                    add_task = True                 
                elif job.export_period == 30 and time.gmtime().tm_yday%30 == 0: # on every 30 days
                    start_time      = '%s %02d:00:00'%((today - timedelta(30)).strftime('%d-%b-%Y'),job.day_time) # "%d-%b-%Y %H:%M:%S"
                    start_time      = mktime(datetime.strptime(start_time, "%d-%b-%Y %H:%M:%S").timetuple())
                    filename_suffix = '30_day_export_%d_%s'%(job.pk,job.label)
                    add_task = True
                    
                if job.day_time == 0:
                    end_time    = '%s %02d:59:59'%((today - timedelta(1)).strftime('%d-%b-%Y'),23) # "%d-%b-%Y %H:%M:%S"
                else:
                    end_time    = '%s %02d:59:59'%(today.strftime('%d-%b-%Y'),job.day_time-1) # "%d-%b-%Y %H:%M:%S"
                end_time    = mktime(datetime.strptime(end_time, "%d-%b-%Y %H:%M:%S").timetuple())
                # create ExportTask
                if add_task:

                    et = ExportTask(\
                        label = filename_suffix,\
                        datetime_max = datetime.fromtimestamp(end_time,UTC),\
                        datetime_min = datetime.fromtimestamp(start_time,UTC),\
                        filename_suffix = filename_suffix,\
                        mean_value_period = job.mean_value_period,\
                        file_format = job.file_format,\
                        datetime_start = datetime.fromtimestamp(end_time+60,UTC)\
                        )
                    et.save()
                    
                    et.variables.add(*job.variables.all())
                
                
        ## check runnging tasks and start the next Export Task
        running_jobs = ExportTask.objects.filter(busy=True,failed=False)
        if running_jobs:
            for job in running_jobs:
                if time() - job.start() < 30:
                    # only check Task wenn it is running longer then 30s
                    continue

                if job.backgroundtask is None:
                    # if the job has no backgroundtask assosiated mark as failed
                    job.failed = True
                    job.save()
                    continue
                
                if time() - job.backgroundtask.timestamp < 60:
                    # if the backgroundtask has been updated in the past 60s wait
                    continue
                
                if job.backgroundtask.pid == 0:
                    # if the job has no valid pid mark as failed
                    job.failed = True
                    job.save()
                    continue
                
                # check if process is alive
                try:
                    os.kill(job.backgroundtask.pid, 0)
                except OSError:
                    job.failed = True
                    job.save()
                    continue
                
                if time() - job.backgroundtask.timestamp > 60*20:
                    # if there is not update in the last 20 minutes terminate
                    # the process and mark as failed
                    os.kill(job.backgroundtask.pid, 15)
                    job.failed = True
                    job.save()
                    continue
                    
        else:
            # start the next Export Task
            wait_time = 1 # wait one second to start the job
            job = ExportTask.objects.filter(\
                done=False,\
                busy=False,\
                failed=False,\
                datetime_start__lte=datetime.now(UTC)).first() # get all jobs
            if job:
                log.debug(' started Timer %d'%job.pk)
                Timer(wait_time,_export_handler,[job,today]).start()
                if job.datetime_start == None:
                    job.datetime_start = datetime.now(UTC)
                job.busy = True
                job.save()
        
        ## delete all done jobs older the 60 days
        for job in ExportTask.objects.filter(done=True, busy=False, datetime_start__gte=datetime.fromtimestamp(time()+60*24*60*60,UTC)):
            job.delete()
        ## delete all failed jobs older the 60 days
        for job in ExportTask.objects.filter(failed=True, datetime_start__gte=datetime.fromtimestamp(time()+60*24*60*60,UTC)):
            job.delete()
        return None # because we have no data to store



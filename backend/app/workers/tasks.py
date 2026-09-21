from app.workers.celery_app import celery_app

@celery_app.task
def ping_worker():
    return "WORKER_HEARTBEAT_ACK"

@celery_app.task
def sync_assignment_to_servicenow(incident_id, employee_id):
    pass

@celery_app.task
def send_notification_email(user_id, subject, body):
    pass

@celery_app.task
def retry_failed_syncs():
    pass

@celery_app.task
def poll_servicenow_incidents():
    pass

@celery_app.task
def process_new_incident(incident_id):
    pass

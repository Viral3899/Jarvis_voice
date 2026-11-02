"""
Daily Briefing System — automated morning/evening summaries.
"""
import threading
import datetime
import time
from typing import Dict, Any, Optional, TYPE_CHECKING
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from core.config import config
from core.notifier import notify

if TYPE_CHECKING:
    import jarvis as jarvis_main


class BriefingManager:
    """Manages automated daily briefings."""
    
    def __init__(self, jarvis_instance):
        self.jarvis = jarvis_instance
        self.scheduler = BackgroundScheduler()
        self._running = False
        self._last_briefing_date = None
        self._briefing_type = None
    
    def start(self):
        """Start the briefing scheduler."""
        cfg = config.get()
        if not cfg.briefing.enabled:
            return
        
        # Schedule morning briefing
        morning_time = cfg.briefing.morning_time
        hour, minute = map(int, morning_time.split(':'))
        self.scheduler.add_job(
            self._run_briefing,
            CronTrigger(hour=hour, minute=minute),
            args=['morning'],
            id='morning_briefing',
            replace_existing=True
        )
        
        # Schedule evening briefing
        evening_time = cfg.briefing.evening_time
        hour, minute = map(int, evening_time.split(':'))
        self.scheduler.add_job(
            self._run_briefing,
            CronTrigger(hour=hour, minute=minute),
            args=['evening'],
            id='evening_briefing',
            replace_existing=True
        )
        
        self.scheduler.start()
        self._running = True
        print(f"[Briefing] Scheduled: {cfg.briefing.morning_time} (morning), {cfg.briefing.evening_time} (evening)")
    
    def stop(self):
        """Stop the briefing scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        self._running = False
    
    def _run_briefing(self, briefing_type: str):
        """Run a briefing of the specified type."""
        # Prevent duplicate briefings on same day
        today = datetime.date.today()
        if self._last_briefing_date == today and self._briefing_type == briefing_type:
            return
        
        self._last_briefing_date = today
        self._briefing_type = briefing_type
        
        # Run in background thread
        threading.Thread(target=self._execute_briefing, args=(briefing_type,), daemon=True).start()
    
    def _execute_briefing(self, briefing_type: str):
        """Execute the briefing."""
        try:
            # Lazy import to avoid circular dependency
            import jarvis as jarvis_main
            modules = jarvis_main.modules
            
            cfg = config.get()
            include = cfg.briefing.include
            
            parts = []
            
            # Greeting
            if briefing_type == 'morning':
                parts.append("Good morning! Here's your daily briefing.")
            else:
                parts.append("Good evening! Here's your evening summary.")
            
            # Tasks
            if include.get('tasks', True):
                task_summary = self.jarvis.tasks.get_summary()
                parts.append(f"Tasks: {task_summary}")
            
            # Calendar
            if include.get('calendar', True):
                cal = modules.get('calendar')
                if cal:
                    parts.append(f"Calendar: {cal.get_summary()}")
            
            # Email
            if include.get('email', True):
                gmail = modules.get('gmail')
                if gmail:
                    parts.append(f"Email: {gmail.get_summary()}")
            
            # WhatsApp
            if include.get('whatsapp', True):
                wa = modules.get('whatsapp')
                if wa:
                    parts.append(f"WhatsApp: {wa.get_summary()}")
            
            # Combine and speak
            full_briefing = " ".join(parts)
            
            # Send notification
            notify(f"Daily {briefing_type.capitalize()} Briefing", 
                   f"Your {briefing_type} briefing is ready.")
            
            # Speak the briefing
            self.jarvis._say(full_briefing)
            
        except Exception as e:
            print(f"[Briefing] Error: {e}")
    
    def trigger_manual(self, briefing_type: str = 'full'):
        """Manually trigger a briefing."""
        threading.Thread(target=self._execute_briefing, args=(briefing_type,), daemon=True).start()


def create_briefing_manager(jarvis_instance) -> BriefingManager:
    """Factory function to create briefing manager."""
    return BriefingManager(jarvis_instance)
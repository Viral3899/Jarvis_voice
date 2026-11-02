"""
Auto-Start Manager — configure JARVIS to start automatically on Windows boot.
"""
import os
import sys
import subprocess
import winreg
from pathlib import Path
from typing import Optional


class AutoStartManager:
    """Manage Windows auto-start configuration."""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.venv_python = self.project_root / "vvenv" / "Scripts" / "python.exe"
        self.main_script = self.project_root / "jarvis.py"
        self.app_name = "JARVIS_Agent"
    
    def is_venv_valid(self) -> bool:
        """Check if virtual environment exists."""
        return self.venv_python.exists()
    
    def get_startup_command(self) -> str:
        """Get the command to start JARVIS."""
        if self.is_venv_valid():
            return f'"{self.venv_python}" "{self.main_script}"'
        return f'python "{self.main_script}"'
    
    def enable_task_scheduler(self, run_as_admin: bool = False) -> bool:
        """Create a Windows Task Scheduler task for auto-start."""
        try:
            command = self.get_startup_command()
            
            # XML for the task
            task_xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>JARVIS Personal AI Agent - Auto Start</Description>
    <Author>{os.getenv('USERNAME', 'User')}</Author>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{os.getenv('USERNAME', 'User')}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>{'HighestAvailable' if run_as_admin else 'LeastPrivilege'}</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>true</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{command.split()[0]}</Command>
      <Arguments>{' '.join(command.split()[1:])}</Arguments>
      <WorkingDirectory>{self.project_root}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""
            
            # Write XML to temp file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
                f.write(task_xml)
                xml_path = f.name
            
            try:
                # Create the task
                result = subprocess.run([
                    'schtasks', '/Create', '/TN', self.app_name,
                    '/XML', xml_path, '/F'
                ], capture_output=True, text=True)
                
                os.unlink(xml_path)
                
                if result.returncode == 0:
                    print(f"✅ Auto-start enabled via Task Scheduler")
                    return True
                else:
                    print(f"❌ Failed to create task: {result.stderr}")
                    return False
            except Exception as e:
                print(f"❌ Error creating task: {e}")
                return False
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def disable_task_scheduler(self) -> bool:
        """Remove the Task Scheduler task."""
        try:
            result = subprocess.run([
                'schtasks', '/Delete', '/TN', self.app_name, '/F'
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"✅ Auto-start disabled")
                return True
            else:
                print(f"❌ Failed to delete task: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def enable_startup_folder(self) -> bool:
        """Create a shortcut in the Windows Startup folder."""
        try:
            import winshell
            from win32com.client import Dispatch
            
            startup_folder = winshell.startup()
            shortcut_path = os.path.join(startup_folder, f"{self.app_name}.lnk")
            
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.Targetpath = str(self.venv_python) if self.is_venv_valid() else sys.executable
            shortcut.Arguments = f'"{self.main_script}"'
            shortcut.WorkingDirectory = str(self.project_root)
            shortcut.IconLocation = str(self.main_script)
            shortcut.save()
            
            print(f"✅ Auto-start enabled via Startup folder")
            return True
        except ImportError:
            print("❌ Requires pywin32 and winshell: pip install pywin32 winshell")
            return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def disable_startup_folder(self) -> bool:
        """Remove the Startup folder shortcut."""
        try:
            import winshell
            startup_folder = winshell.startup()
            shortcut_path = os.path.join(startup_folder, f"{self.app_name}.lnk")
            
            if os.path.exists(shortcut_path):
                os.remove(shortcut_path)
                print(f"✅ Auto-start disabled")
                return True
            else:
                print("⚠ Shortcut not found")
                return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def enable_registry_run(self) -> bool:
        """Add to HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run."""
        try:
            command = self.get_startup_command()
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, command)
            
            print(f"✅ Auto-start enabled via Registry")
            return True
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def disable_registry_run(self) -> bool:
        """Remove from Registry Run key."""
        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, self.app_name)
            print(f"✅ Auto-start disabled")
            return True
        except FileNotFoundError:
            print("⚠ Registry entry not found")
            return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def is_enabled(self, method: str = "task_scheduler") -> bool:
        """Check if auto-start is enabled."""
        if method == "task_scheduler":
            result = subprocess.run(
                ['schtasks', '/Query', '/TN', self.app_name],
                capture_output=True
            )
            return result.returncode == 0
        elif method == "startup_folder":
            import winshell
            shortcut_path = os.path.join(winshell.startup(), f"{self.app_name}.lnk")
            return os.path.exists(shortcut_path)
        elif method == "registry":
            try:
                key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
                    winreg.QueryValueEx(key, self.app_name)
                return True
            except FileNotFoundError:
                return False
        return False
    
    def enable(self, method: str = "task_scheduler", run_as_admin: bool = False) -> bool:
        """Enable auto-start using specified method."""
        if method == "task_scheduler":
            return self.enable_task_scheduler(run_as_admin)
        elif method == "startup_folder":
            return self.enable_startup_folder()
        elif method == "registry":
            return self.enable_registry_run()
        return False
    
    def disable(self, method: str = "task_scheduler") -> bool:
        """Disable auto-start."""
        if method == "task_scheduler":
            return self.disable_task_scheduler()
        elif method == "startup_folder":
            return self.disable_startup_folder()
        elif method == "registry":
            return self.disable_registry_run()
        return False


def setup_autostart(method: str = "task_scheduler", run_as_admin: bool = False) -> bool:
    """Convenience function to set up auto-start."""
    manager = AutoStartManager()
    return manager.enable(method, run_as_admin)


def remove_autostart(method: str = "task_scheduler") -> bool:
    """Convenience function to remove auto-start."""
    manager = AutoStartManager()
    return manager.disable(method)
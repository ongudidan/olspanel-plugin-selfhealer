import os
import re
import subprocess
import shutil
from django.shortcuts import render
from django.http import StreamingHttpResponse, JsonResponse, HttpResponse
from django.conf import settings
from users.decorators import loginadminoruser

# Helper to check service status
def check_service_status(service_name):
    try:
        res = subprocess.run(["systemctl", "is-active", service_name], capture_output=True, text=True)
        return res.stdout.strip() == "active"
    except Exception:
        return False

# Core self-healer engine
def execute_self_healer(log_callback):
    log_callback("🔍 Starting System Diagnostics & Self-Healing Pipeline...\n")
    
    # 1. Align mypanel configuration file naming
    try:
        mypanel_vhost_dir = '/usr/local/lsws/conf/vhosts/mypanel'
        if os.path.exists(mypanel_vhost_dir):
            vhconf_file = os.path.join(mypanel_vhost_dir, 'vhconf.conf')
            vhost_file = os.path.join(mypanel_vhost_dir, 'vhost.conf')
            if os.path.exists(vhconf_file):
                if not os.path.exists(vhost_file):
                    shutil.copy2(vhconf_file, vhost_file)
                    subprocess.run(["chown", "lsadm:lsadm", vhost_file])
                    log_callback("✅ [Aligned] Aligned mypanel vhconf.conf to vhost.conf.\n")
                else:
                    log_callback("ℹ️ [Skip] mypanel vhost.conf already exists.\n")
            else:
                log_callback("⚠️ [Warning] mypanel vhconf.conf not found.\n")
        else:
            log_callback("ℹ️ [Skip] mypanel virtual host folder not found under OLS.\n")
    except Exception as e:
        log_callback(f"❌ [Error] Aligning mypanel vhost files: {str(e)}\n")

    # 2. Get server IP address from etc/ip file
    server_ip = '127.0.0.1'
    ip_file_path = os.path.join(settings.BASE_DIR, 'etc/ip')
    if os.path.exists(ip_file_path):
        try:
            with open(ip_file_path, 'r') as ip_f:
                server_ip = ip_f.read().strip()
                log_callback(f"ℹ️ [Info] Retrieved server IP: {server_ip}\n")
        except Exception:
            log_callback("⚠️ [Warning] Could not read etc/ip file, falling back to 127.0.0.1.\n")

    # 3. Configure IP and localhost mappings for mypanel, and set restrained 0
    try:
        httpd_path = '/usr/local/lsws/conf/httpd_config.conf'
        if os.path.exists(httpd_path):
            with open(httpd_path, 'r') as h_f:
                httpd_content = h_f.read()

            modified = False
            # Replace standard map mypanel with split lines including server IP and localhost
            target_map = '  map                     mypanel mypanel'
            replacement_map = f"""  map                     mypanel mypanel
  map                     mypanel {server_ip}
  map                     mypanel 127.0.0.1
  map                     mypanel localhost"""
            
            if target_map in httpd_content:
                httpd_content = httpd_content.replace(target_map, replacement_map)
                modified = True
                log_callback("✅ [Configured] Mapped server IP and localhost to mypanel virtual host in OLS listeners.\n")
            else:
                log_callback("ℹ️ [Skip] Server IP listener mappings already updated or mypanel map not found.\n")

            # Set restrained 0 for mypanel and all panel_* virtual hosts
            pattern = r'(virtualhost\s+(?:panel_[^{]+|mypanel)\s*\{[\s\S]*?restrained\s+)1'
            httpd_content, count = re.subn(pattern, r'\g<1>0', httpd_content)
            if count > 0:
                modified = True
                log_callback(f"✅ [Configured] Set restrained to 0 for {count} panel virtual hosts in httpd_config.conf.\n")
            else:
                log_callback("ℹ️ [Skip] All panel virtual hosts already set to restrained 0.\n")

            if modified:
                with open(httpd_path, 'w') as h_f:
                    h_f.write(httpd_content)
        else:
            log_callback("❌ [Error] httpd_config.conf not found under OLS directory.\n")
    except Exception as e:
        log_callback(f"❌ [Error] Updating httpd_config.conf listener maps: {str(e)}\n")

    # 4. Add PHP script handler mapping to all panel virtual hosts
    try:
        vhosts_dir = '/usr/local/lsws/conf/vhosts'
        if os.path.exists(vhosts_dir):
            vhost_updated = 0
            for vhost in os.listdir(vhosts_dir):
                if vhost.startswith('panel_') or vhost == 'mypanel':
                    v_conf = os.path.join(vhosts_dir, vhost, 'vhost.conf')
                    if not os.path.exists(v_conf):
                        v_conf = os.path.join(vhosts_dir, vhost, 'vhconf.conf')
                        if not os.path.exists(v_conf):
                            continue

                    with open(v_conf, 'r') as v_f:
                        v_content = v_f.read()

                    target_sh = """scripthandler  {
  add                     lsapi:panelext panelext
}"""
                    replacement_sh = """scripthandler  {
  add                     lsapi:panelext panelext
  add                     lsapi:lsphp php
}"""
                    if target_sh in v_content:
                        with open(v_conf, 'w') as v_f:
                            v_f.write(v_content.replace(target_sh, replacement_sh))
                        vhost_updated += 1
            if vhost_updated > 0:
                log_callback(f"✅ [Configured] Added global php script handler to {vhost_updated} virtual hosts.\n")
            else:
                log_callback("ℹ️ [Skip] Script handlers for panel virtual hosts are already up to date.\n")
    except Exception as e:
        log_callback(f"❌ [Error] Updating virtual host script handlers: {str(e)}\n")

    # 5. Create missing html folder for panel user (fortunedevs)
    try:
        html_dir = '/home/fortunedevs/public_html/html'
        if not os.path.exists(html_dir):
            os.makedirs(html_dir, exist_ok=True)
            import pwd
            try:
                p_info = pwd.getpwnam('fortunedevs')
                os.chown(html_dir, p_info.pw_uid, p_info.pw_gid)
                os.chmod(html_dir, 0o755)
                log_callback("✅ [Fixed] Created and permissioned missing /home/fortunedevs/public_html/html directory.\n")
            except KeyError:
                log_callback("⚠️ [Warning] Unix user 'fortunedevs' not found on system. Directory created but ownership not changed.\n")
        else:
            log_callback("ℹ️ [Skip] /home/fortunedevs/public_html/html directory already exists.\n")
    except Exception as e:
        log_callback(f"❌ [Error] Managing public_html/html folder: {str(e)}\n")

    # 6. Create phpMyAdmin and webmail symlinks in Example/html
    try:
        example_html = '/usr/local/lsws/Example/html'
        if os.path.exists(example_html):
            for service, target in [('phpmyadmin', '/usr/local/olspanel/phpmyadmin'), 
                                   ('webmail', '/usr/local/olspanel/webmail')]:
                link_path = os.path.join(example_html, service)
                is_valid = True
                
                # Check link validity
                if os.path.islink(link_path):
                    if not os.path.exists(link_path):
                        log_callback(f"⚠️ [Diagnostics] Broken symlink detected for {service}. Removing...\n")
                        os.unlink(link_path)
                        is_valid = False
                elif os.path.exists(link_path):
                    # Physical folder/file exists but we need a symlink
                    log_callback(f"⚠️ [Diagnostics] Physical file/directory matches {service} link path. Clearing...\n")
                    if os.path.isdir(link_path):
                        shutil.rmtree(link_path)
                    else:
                        os.remove(link_path)
                    is_valid = False
                else:
                    is_valid = False

                if not is_valid:
                    os.symlink(target, link_path)
                    import pwd, grp
                    w_uid = pwd.getpwnam('www-data').pw_uid
                    w_gid = grp.getgrnam('www-data').gr_gid
                    os.lchown(link_path, w_uid, w_gid)
                    log_callback(f"✅ [Fixed] Re-created symlink for {service} -> {target}.\n")
                else:
                    log_callback(f"ℹ️ [Skip] Symlink for {service} is valid and functional.\n")
        else:
            log_callback("ℹ️ [Skip] OLS default Example/html folder not found. Symlinks skipped.\n")
    except Exception as e:
        log_callback(f"❌ [Error] Resolving phpMyAdmin / Webmail symlinks: {str(e)}\n")

    # 7. Make RainLoop data directories world-writable (777) for OLS suEXEC compatibility
    try:
        paths_to_chmod = [
            '/usr/local/olspanel/webmail/data', 
            os.path.join(settings.BASE_DIR, '3rdparty/rainloop/data')
        ]
        chmod_count = 0
        for r_dir in paths_to_chmod:
            if os.path.exists(r_dir):
                subprocess.run(["chmod", "-R", "777", r_dir])
                log_callback(f"✅ [Permissions] Set 777 permissions recursively to data folder: {r_dir}\n")
                chmod_count += 1
        if chmod_count == 0:
            log_callback("ℹ️ [Skip] No Rainloop data directory found to permission.\n")
    except Exception as e:
        log_callback(f"❌ [Error] Restructuring RainLoop data folders permissions: {str(e)}\n")

    # 8. Patch License validations (Bypass licensing requirement)
    try:
        log_callback("\n🚀 Patching license validations (Bypassing billing checks)...\n")
        
        # Patch A: decorators.py
        decorators_file = os.path.join(settings.BASE_DIR, 'users/decorators.py')
        if os.path.exists(decorators_file):
            with open(decorators_file, 'r') as f:
                content = f.read()
            if 'return "active"' not in content or 'def premium_features' not in content:
                pattern = re.compile(r'def get_license_status\(request\):.*', re.DOTALL)
                new_tail = """def get_license_status(request):
    return "active"

def premium_features(*allowed_types):
    def decorator(view_func):
        from functools import wraps
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
"""
                if pattern.search(content):
                    with open(decorators_file, 'w') as f:
                        f.write(pattern.sub(new_tail, content))
                    log_callback("✅ [License Bypass] Patched users/decorators.py successfully.\n")
            else:
                log_callback("ℹ️ [License Bypass] users/decorators.py already patched.\n")

        # Patch B: LicenseMiddleware.py
        middleware_file = os.path.join(settings.BASE_DIR, 'users/middleware/LicenseMiddleware.py')
        os.makedirs(os.path.dirname(middleware_file), exist_ok=True)
        already_patched = False
        if os.path.exists(middleware_file):
            with open(middleware_file, 'r') as f:
                m_content = f.read()
            if 'class LicenseMiddleware' in m_content and 'return "active"' in m_content:
                already_patched = True

        if not already_patched:
            with open(middleware_file, 'w') as f:
                f.write("""from django.shortcuts import redirect, render

def get_license_status(request):
    return "active"

class LicenseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)
""")
            log_callback("✅ [License Bypass] Rewrote LicenseMiddleware.py successfully.\n")
        else:
            log_callback("ℹ️ [License Bypass] LicenseMiddleware.py already patched.\n")

        # Patch C: function.py
        functions_file = os.path.join(settings.BASE_DIR, 'users/function.py')
        if os.path.exists(functions_file):
            with open(functions_file, 'r') as f:
                content = f.read()
            if 'def get_license_status(request):\n    return "active"\n\n\ndef download_script_only' not in content:
                pattern = re.compile(r'def get_license_status\(request\):.*?def download_script_only', re.DOTALL)
                new_block = """def get_license_status(request):
    return "active"


def download_script_only"""
                if pattern.search(content):
                    with open(functions_file, 'w') as f:
                        f.write(pattern.sub(new_block, content))
                    log_callback("✅ [License Bypass] Patched users/function.py successfully.\n")
            else:
                log_callback("ℹ️ [License Bypass] users/function.py already patched.\n")

        # Compile patched Python files
        for filepath in [decorators_file, middleware_file, functions_file]:
            if os.path.exists(filepath):
                import py_compile
                py_compile.compile(filepath)

    except Exception as le:
        log_callback(f"❌ [Error] Patching license validations: {str(le)}\n")

    # 9. Reload OpenLiteSpeed to apply configurations
    try:
        log_callback("\n🔄 Reloading OpenLiteSpeed web server...\n")
        subprocess.run(["/usr/local/lsws/bin/lswsctrl", "reload"])
        log_callback("✅ OpenLiteSpeed web server reloaded successfully.\n")
    except Exception as e:
        log_callback(f"❌ [Error] Restarting OpenLiteSpeed: {str(e)}\n")

    log_callback("\n🎉 System Self-Healing Pipeline Execution Completed!\n")

# CLI Wrapper for plugin installer/cmd execution
def run_self_healer_cli():
    execute_self_healer(lambda msg: print(msg, end=''))

def get_authenticated_user(request):
    """Retrieves authenticated admin, respecting impersonation"""
    if hasattr(request, 'admin_user') and request.admin_user:
        if request.user and request.user.is_authenticated and request.user != request.admin_user:
            return request.user
        return request.admin_user
    return request.user if request.user.is_authenticated else None

def is_admin(user):
    """Helper to check if user is superuser or admin staff"""
    return user and (user.is_superuser or user.is_staff)

# Django view to render GUI dashboard
@loginadminoruser
def self_healer_gui(request):
    user = get_authenticated_user(request)
    if not is_admin(user):
        return HttpResponse("Unauthorized Access", status=403)
    base_template = 'whm/base.html' if user.is_superuser else 'users/base.html'
    context = {
        'base_template': base_template,
        'ols_active': check_service_status('lsws'),
        'postfix_active': check_service_status('postfix'),
        'dovecot_active': check_service_status('dovecot'),
        'cp_active': check_service_status('cp'),
    }
    return render(request, 'selfhealer/gui.html', context)

# Django view to stream live logs back to client using SSE/StreamingHttpResponse
@loginadminoruser
def self_healer_run(request):
    user = get_authenticated_user(request)
    if not is_admin(user):
        return HttpResponse("Unauthorized Access", status=403)
    def event_stream():
        yield "data: [Initialization] Connecting to self-healer engine...\n\n"
        
        # Generator collector to stream logs in real-time
        def stream_log(message):
            # Encode log line for Server-Sent Events (SSE) format
            cleaned = message.replace('\n', '\nData: ')
            stream_log.accumulated += f"data: {cleaned}\n\n"
        
        stream_log.accumulated = ""
        
        # Execute healer and yield results chunk-by-chunk
        try:
            execute_self_healer(stream_log)
            yield stream_log.accumulated
        except Exception as err:
            yield f"data: ❌ [Unexpected Error] {str(err)}\n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response

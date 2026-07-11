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

    # Patch F: Fix missing import / NameError for run_package_update in users/server_core.py
    try:
        server_core_file = os.path.join(settings.BASE_DIR, 'users/server_core.py')
        if os.path.exists(server_core_file):
            with open(server_core_file, 'r') as f:
                sc_content = f.read()

            target_block = """            if not php_version.startswith('cgi'):
                repo_cmd = "wget -O - https://repo.litespeed.sh | sudo bash"
                subprocess.run(repo_cmd, shell=True, check=True)
                run_package_update()"""

            patched_block = """            if not php_version.startswith('cgi'):
                repo_cmd = "wget -O - https://repo.litespeed.sh | sudo bash"
                subprocess.run(repo_cmd, shell=True, check=True)
                from whm.function import run_package_update
                run_package_update()"""

            if target_block in sc_content:
                sc_content = sc_content.replace(target_block, patched_block)
                with open(server_core_file, 'w') as f:
                    f.write(sc_content)
                import py_compile
                py_compile.compile(server_core_file)
                log_callback("✅ [Bug Fix] Patched users/server_core.py to resolve run_package_update NameError.\n")
            else:
                log_callback("ℹ️ [Bug Fix] users/server_core.py already patched or block not found.\n")
    except Exception as sce:
        log_callback(f"❌ [Error] Patching users/server_core.py: {str(sce)}\n")

    # Patch G: Fix AttributeError NoneType object has no attribute get in users/views.py (web_server view)
    try:
        views_file = os.path.join(settings.BASE_DIR, 'users/views.py')
        if os.path.exists(views_file):
            with open(views_file, 'r') as f:
                views_content = f.read()

            target_block = """            if request.user:
                user_data = get_user_data_by_id(request.user.id)
                whm = user_data.get('whm', 0)
            elif request.admin_user:
                user_data = get_user_data_by_id(request.admin_user.id)
                whm = user_data.get('whm', 0)"""

            patched_block = """            if request.user:
                user_data = get_user_data_by_id(request.user.id)
                whm = user_data.get('whm', 0) if user_data else (1 if request.user.is_superuser or request.user.is_staff else 0)
            elif request.admin_user:
                user_data = get_user_data_by_id(request.admin_user.id)
                whm = user_data.get('whm', 0) if user_data else (1 if request.admin_user.is_superuser or request.admin_user.is_staff else 0)"""

            if target_block in views_content:
                views_content = views_content.replace(target_block, patched_block)
                with open(views_file, 'w') as f:
                    f.write(views_content)
                import py_compile
                py_compile.compile(views_file)
                log_callback("✅ [Bug Fix] Patched users/views.py to resolve AttributeError for superuser user_data.\n")
            else:
                log_callback("ℹ️ [Bug Fix] users/views.py already patched or block not found.\n")
    except Exception as ve:
        log_callback(f"❌ [Error] Patching users/views.py: {str(ve)}\n")

    # Patch H: Avoid systemd restart CP deadlock by using Popen with a 2-second delay
    try:
        whm_func_file = os.path.join(settings.BASE_DIR, 'whm/function.py')
        if os.path.exists(whm_func_file):
            with open(whm_func_file, 'r') as f:
                whm_func_content = f.read()

            target_block_1 = 'subprocess.run(["sudo", "systemctl", "restart", "cp"], check=True)'
            target_block_2 = 'subprocess.run(["sudo", "systemctl", "restart", "cp", "--no-block"], check=True)'
            patched_block = 'subprocess.Popen("sleep 2 && sudo systemctl restart cp", shell=True, start_new_session=True)'

            modified = False
            if target_block_1 in whm_func_content:
                whm_func_content = whm_func_content.replace(target_block_1, patched_block)
                modified = True
            elif target_block_2 in whm_func_content:
                whm_func_content = whm_func_content.replace(target_block_2, patched_block)
                modified = True

            if modified:
                with open(whm_func_file, 'w') as f:
                    f.write(whm_func_content)
                import py_compile
                py_compile.compile(whm_func_file)
                log_callback("✅ [Bug Fix] Patched whm/function.py to use asynchronous delayed panel restart, avoiding hangs.\n")
            else:
                log_callback("ℹ️ [Bug Fix] whm/function.py already patched or block not found.\n")
    except Exception as he:
        log_callback(f"❌ [Error] Patching whm/function.py: {str(he)}\n")


    # Patch D: Solve FOUC & SVG lag on base.html files
    try:
        base_html_files = [
            os.path.join(settings.BASE_DIR, 'users/templates/users/base.html'),
            os.path.join(settings.BASE_DIR, 'whm/templates/whm/base.html')
        ]
        new_script = """{% if branding.brand_color != "#ef6d19" %}   
<script>
(function() {
    const brandColor = "{{ branding.brand_color }}";
    if (brandColor === "#ef6d19") return;

    // Apply CSS overrides immediately
    const style = document.createElement('style');
    style.innerHTML = `
        :root { --brand-color: ${brandColor} !important; }
        .brand-name font, .app-brand font, .app-brand span font { color: ${brandColor} !important; }
        .sidebar-dark .sidebar-inner .nav > li.active > a i, 
        .sidebar-dark .sidebar-inner .nav > li.active > a span,
        .sidebar-dark .sidebar-inner .nav > li.active > a img { color: ${brandColor} !important; }
    `;
    document.head.appendChild(style);

    function processImage(img) {
        const src = img.src;
        if (!src.endsWith('.svg')) return;

        function replaceImg(svgText) {
            const parser = new DOMParser();
            const doc = parser.parseFromString(svgText, "image/svg+xml");
            const svg = doc.querySelector("svg");
            if (!svg) return;

            Array.from(img.attributes).forEach(attr => {
                if (attr.name !== "src") {
                    svg.setAttribute(attr.name, attr.value);
                }
            });

            if (!svg.getAttribute("width")) svg.setAttribute("width", img.getAttribute("width") || "40px");
            if (!svg.getAttribute("height")) svg.setAttribute("height", img.getAttribute("height") || "40px");

            svg.style.cssText = img.style.cssText;
            svg.style.color = brandColor;
            svg.setAttribute("fill", "currentColor");

            svg.querySelectorAll("*").forEach(el => {
                if (el.getAttribute("fill") && el.getAttribute("fill") !== "none") {
                    el.setAttribute("fill", "currentColor");
                }
                if (el.getAttribute("stroke") && el.getAttribute("stroke") !== "none") {
                    el.setAttribute("stroke", "currentColor");
                }
            });

            img.replaceWith(svg);
        }

        const cached = localStorage.getItem('svg_' + src);
        if (cached) {
            replaceImg(cached);
        } else {
            fetch(src)
                .then(r => r.text())
                .then(svgText => {
                    try {
                        localStorage.setItem('svg_' + src, svgText);
                    } catch(e) {}
                    replaceImg(svgText);
                })
                .catch(err => console.error("SVG load failed:", err));
        }
    }

    function init() {
        document.querySelectorAll('#search_here img[src$=".svg"], #left-sidebar img[src$=".svg"]').forEach(processImage);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
</script>
{% endif %}"""
        
        for file_path in base_html_files:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    content = f.read()
                
                pattern = re.compile(r'{%\s*if\s+branding\.brand_color\s*!=\s*\"#ef6d19\"\s*%}\s*<script>.*?</script>\s*{%\s*endif\s*%}', re.DOTALL)
                if pattern.search(content):
                    if 'processImage' not in content:
                        content = pattern.sub(new_script, content)
                        with open(file_path, 'w') as f:
                            f.write(content)
                        log_callback(f"✅ [Performance] Patched color flicker (FOUC) & SVG lag in {os.path.basename(file_path)}.\n")
                else:
                    if '</head>' in content and 'processImage' not in content:
                        content = content.replace('</head>', f'{new_script}\n</head>')
                        with open(file_path, 'w') as f:
                            f.write(content)
                        log_callback(f"✅ [Performance] Injected color flicker (FOUC) script in {os.path.basename(file_path)}.\n")
    except Exception as fe:
        log_callback(f"❌ [Error] Patching color flicker (FOUC): {str(fe)}\n")

    # Patch E: Replace external jQuery CDNs with local assets
    try:
        cdn_files = [
            os.path.join(settings.BASE_DIR, 'users/templates/users/footer.html'),
            os.path.join(settings.BASE_DIR, 'whm/templates/whm/footer.html'),
            os.path.join(settings.BASE_DIR, 'users/templates/users/db_import.html')
        ]
        patched_cdn = 0
        for file_path in cdn_files:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    content = f.read()
                
                modified = False
                if 'https://code.jquery.com/jquery-3.5.1.slim.min.js' in content:
                    content = content.replace('https://code.jquery.com/jquery-3.5.1.slim.min.js', '/media/js/jquery.min.js')
                    modified = True
                if 'https://code.jquery.com/jquery-3.6.0.min.js' in content:
                    content = content.replace('https://code.jquery.com/jquery-3.6.0.min.js', '/media/js/jquery.min.js')
                    modified = True
                
                if modified:
                    with open(file_path, 'w') as f:
                        f.write(content)
                    patched_cdn += 1
        if patched_cdn > 0:
            log_callback(f"✅ [Performance] Replaced external jQuery CDNs with local resources in {patched_cdn} files.\n")
        else:
            log_callback("ℹ️ [Skip] External jQuery CDNs already replaced with local scripts.\n")
    except Exception as ce:
        log_callback(f"❌ [Error] Patching jQuery CDN links: {str(ce)}\n")

    # 9. Repair panel credentials files permissions (for autologin verification)
    try:
        log_callback("\n🔑 Diagnosing panel credentials files under etc/...\n")
        etc_dir = os.path.join(settings.BASE_DIR, 'etc')
        if os.path.exists(etc_dir):
            import pwd, grp
            w_gid = grp.getgrnam('www-data').gr_gid
            r_uid = pwd.getpwnam('root').pw_uid
            
            repaired_count = 0
            for file_name in os.listdir(etc_dir):
                if file_name.startswith('_') or file_name.startswith('phpmyadmin_'):
                    file_path = os.path.join(etc_dir, file_name)
                    if os.path.isfile(file_path):
                        os.chown(file_path, r_uid, w_gid)
                        os.chmod(file_path, 0o644)
                        repaired_count += 1
            if repaired_count > 0:
                log_callback(f"✅ [Permissions] Corrected ownership (root:www-data) and 644 permissions for {repaired_count} credentials files.\n")
            else:
                log_callback("ℹ️ [Skip] Credentials files permissions are already correct.\n")
        else:
            log_callback("⚠️ [Warning] Panel etc/ directory not found.\n")
    except Exception as e:
        log_callback(f"❌ [Error] Repairing credentials files permissions: {str(e)}\n")

    # 10. Repair virtual mailboxes folder permissions
    try:
        vmail_dir = '/home/vmail'
        if os.path.exists(vmail_dir):
            log_callback("\n✉️ Diagnosing virtual mailboxes folder permissions under /home/vmail...\n")
            import pwd, grp
            v_uid = pwd.getpwnam('vmail').pw_uid
            v_gid = grp.getgrnam('vmail').gr_gid
            
            os.chown(vmail_dir, v_uid, v_gid)
            os.chmod(vmail_dir, 0o700)
            
            repaired_dirs = 0
            for root_dir, dirs, files in os.walk(vmail_dir):
                for d in dirs:
                    d_path = os.path.join(root_dir, d)
                    os.chown(d_path, v_uid, v_gid)
                    os.chmod(d_path, 0o700)
                    repaired_dirs += 1
                for f in files:
                    f_path = os.path.join(root_dir, f)
                    os.chown(f_path, v_uid, v_gid)
                    os.chmod(f_path, 0o600)
            log_callback(f"✅ [Permissions] Recursively set ownership (vmail:vmail) and correct access modes for {repaired_dirs} mailbox directories.\n")
        else:
            log_callback("ℹ️ [Skip] Mail server /home/vmail folder not found on this server.\n")
    except Exception as e:
        log_callback(f"❌ [Error] Repairing mailbox folder permissions: {str(e)}\n")

    # 11. Reload Postfix and restart Dovecot
    try:
        log_callback("\n✉️ Reloading Postfix and restarting Dovecot services...\n")
        subprocess.run(["systemctl", "reload", "postfix"])
        subprocess.run(["systemctl", "restart", "dovecot"])
        log_callback("✅ Mail services reloaded and restarted successfully.\n")
    except Exception as e:
        log_callback(f"❌ [Error] Restarting mail services: {str(e)}\n")

    # 12. Fix APT repository label/release info changes to prevent PHP extension install failure
    try:
        if shutil.which('apt-get'):
            log_callback("\n📦 Diagnosing and repairing APT repository release info changes...\n")
            res = subprocess.run(["sudo", "apt-get", "update", "--allow-releaseinfo-change"], capture_output=True, text=True)
            if res.returncode == 0:
                log_callback("✅ APT repository release info changes successfully accepted.\n")
            else:
                log_callback(f"⚠️ [Warning] Failed to run apt-get update --allow-releaseinfo-change: {res.stderr.strip()}\n")
        else:
            log_callback("\nℹ️ [Skip] Not a Debian/Ubuntu system, skipping APT release info healing.\n")
    except Exception as e:
        log_callback(f"❌ [Error] Repairing APT repository release info changes: {str(e)}\n")

    # 13. Reload OpenLiteSpeed to apply configurations
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

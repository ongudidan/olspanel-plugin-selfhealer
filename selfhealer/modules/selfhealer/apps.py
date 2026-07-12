from django.apps import AppConfig

class SelfHealerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'modules.selfhealer'

    def ready(self):
        # Hook into WHM plugins list API view in-memory to dynamically discover and register all local modules
        try:
            from whm import views as whm_views
            from django.http import JsonResponse
            import os
            import json

            current_api_plugins = whm_views.api_plugins

            def patched_api_plugins(request):
                response = current_api_plugins(request)
                if isinstance(response, JsonResponse):
                    try:
                        data = json.loads(response.content.decode('utf-8'))
                        if data.get('success'):
                            plugins = data.get('plugins', [])
                            existing_paths = {p.get('path') for p in plugins if p.get('path')}
                            existing_names = {p.get('name', '').lower() for p in plugins}

                            modules_dir = "/usr/local/olspanel/mypanel/modules"

                            known_meta = {
                                "selfhealer": {
                                    "name": "System Self-Healer",
                                    "category": "Terminal",
                                    "image": "/media/icon/selfhealer.svg",
                                    "url": "/module/selfhealer/gui/"
                                }
                            }

                            terminal_cat_id = 3
                            for p in plugins:
                                if p.get('category', '').lower() == 'terminal':
                                    terminal_cat_id = p.get('category_id', 3)
                                    break

                            if os.path.exists(modules_dir):
                                for name in os.listdir(modules_dir):
                                    mod_path = os.path.join(modules_dir, name)
                                    if os.path.isdir(mod_path) and name not in ['.', '..', '__pycache__', 'webterminal']:
                                        meta = known_meta.get(name, {})
                                        display_name = meta.get("name") or name.replace('_', ' ').replace('-', ' ').title()
                                        
                                        # Skip duplicates by path, name, or slug name
                                        if mod_path not in existing_paths and display_name.lower() not in existing_names and name.lower() not in existing_names:
                                            category = meta.get("category") or "Terminal"
                                            url_val = meta.get("url") or ""

                                            # Find image
                                            icon_path = meta.get("image")
                                            if not icon_path:
                                                if os.path.exists(f"/usr/local/olspanel/mypanel/media/icon/{name}.svg"):
                                                    icon_path = f"/media/icon/{name}.svg"
                                                elif os.path.exists(f"/usr/local/olspanel/mypanel/media/icon/{name}.png"):
                                                    icon_path = f"/media/icon/{name}.png"
                                                else:
                                                    icon_path = "/media/icon/extension.svg"

                                            custom_plugin = {
                                                "id": 300 + len(plugins),
                                                "name": f"{display_name}<style>#pluginList > div {{ display: flex !important; flex-direction: column !important; height: 380px !important; }} #pluginList > div > img {{ margin-top: auto !important; }}</style>",
                                                "category": category,
                                                "category_id": terminal_cat_id,
                                                "type": "free",
                                                "url": url_val,
                                                "path": mod_path,
                                                "image": icon_path,
                                                "pre_build_path": "",
                                                "is_installed": True,
                                                "license_valid": True
                                            }
                                            plugins.append(custom_plugin)
                                            existing_paths.add(mod_path)
                                            existing_names.add(display_name.lower())

                            data['plugins'] = plugins
                            data['count'] = len(plugins)
                            response.content = json.dumps(data).encode('utf-8')
                    except Exception:
                        pass
                return response

            whm_views.api_plugins = patched_api_plugins
            print("[SystemSelfHealer] Successfully registered in-memory plugin auto-discovery hook.")
        except Exception as patch_err:
            print(f"[SystemSelfHealer] Plugin auto-discovery hook registration warning: {patch_err}")

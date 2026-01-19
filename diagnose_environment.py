#!/usr/bin/env python3
"""
Environment Diagnostic Script

Shows detailed information about the Python environment to help debug
issues with module loading and virtual environment configuration.

Run this to understand which Python/packages are being used.
"""

import sys
import os

def print_header(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)

def print_section(title):
    print(f"\n--- {title} ---")

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    print_header("ENVIRONMENT DIAGNOSTIC")
    
    # ==========================================================================
    # PYTHON EXECUTABLE
    # ==========================================================================
    print_section("Python Executable")
    print(f"sys.executable: {sys.executable}")
    print(f"sys.version: {sys.version}")
    
    # Check if in venv
    in_venv = (
        hasattr(sys, 'real_prefix') or 
        (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    )
    print(f"In virtual environment: {in_venv}")
    
    if in_venv:
        print(f"  sys.prefix: {sys.prefix}")
        if hasattr(sys, 'base_prefix'):
            print(f"  sys.base_prefix: {sys.base_prefix}")
    
    # ==========================================================================
    # PROJECT VENV CHECK
    # ==========================================================================
    print_section("Project Virtual Environment")
    
    venv_dir = os.path.join(script_dir, ".venv")
    venv_python = os.path.join(venv_dir, "bin", "python")
    
    print(f"Expected venv: {venv_dir}")
    print(f"Venv exists: {os.path.exists(venv_dir)}")
    print(f"Venv python exists: {os.path.exists(venv_python)}")
    
    # Check if current Python is from project venv
    is_project_venv = os.path.normpath(sys.executable).startswith(os.path.normpath(venv_dir))
    print(f"Running from project venv: {is_project_venv}")
    
    if not is_project_venv:
        print("\n  ⚠️  WARNING: Not using project's virtual environment!")
        print(f"  Current Python: {sys.executable}")
        print(f"  Expected:       {venv_python}")
        print("\n  To fix:")
        print(f"    cd {script_dir}")
        print("    ./run_in_venv.sh diagnose_environment.py")
    
    # ==========================================================================
    # SYS.PATH
    # ==========================================================================
    print_section("sys.path (first 10 entries)")
    for i, path in enumerate(sys.path[:10]):
        marker = ""
        if ".venv" in path or "venv" in path:
            marker = " ← VENV"
        elif "site-packages" in path:
            marker = " ← site-packages"
        print(f"  [{i}] {path}{marker}")
    
    if len(sys.path) > 10:
        print(f"  ... and {len(sys.path) - 10} more")
    
    # ==========================================================================
    # KEY PACKAGES
    # ==========================================================================
    print_section("Key Package Locations")
    
    packages = ['ftrack_api', 'PySide6', 'requests', 'arrow']
    
    for pkg_name in packages:
        try:
            pkg = __import__(pkg_name)
            location = getattr(pkg, '__file__', 'built-in')
            version = getattr(pkg, '__version__', 'unknown')
            
            # Check if from venv
            is_from_venv = location and ('.venv' in location or 'venv' in location)
            marker = " ✓" if is_from_venv else ""
            
            print(f"  {pkg_name}:{marker}")
            print(f"    Version:  {version}")
            print(f"    Location: {location}")
            
        except ImportError as e:
            print(f"  {pkg_name}: NOT FOUND ({e})")
    
    # ==========================================================================
    # PROJECT MODULES
    # ==========================================================================
    print_section("Project Module Imports")
    
    # Ensure project is in path
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    
    modules = [
        'src.core.ftrack_manager',
        'src.gui.main_window',
        'src.config.credentials_manager'
    ]
    
    for mod_name in modules:
        try:
            mod = __import__(mod_name, fromlist=[''])
            location = getattr(mod, '__file__', 'unknown')
            print(f"  ✓ {mod_name}")
            print(f"    {location}")
        except ImportError as e:
            print(f"  ✗ {mod_name}: {e}")
    
    # ==========================================================================
    # ENVIRONMENT VARIABLES
    # ==========================================================================
    print_section("Relevant Environment Variables")
    
    env_vars = [
        'FLAME_FTRACK_DIR',
        'FTRACK_SERVER',
        'FTRACK_API_USER',
        'FTRACK_API_KEY',
        'PYTHONPATH',
        'VIRTUAL_ENV',
        'PATH'
    ]
    
    for var in env_vars:
        value = os.environ.get(var, '')
        if var == 'FTRACK_API_KEY' and value:
            value = value[:8] + '...' + value[-4:] if len(value) > 12 else '***'
        elif var == 'PATH':
            # Just show first few entries
            paths = value.split(':')[:3]
            value = ':'.join(paths) + '...' if len(value.split(':')) > 3 else value
        elif var == 'PYTHONPATH':
            paths = value.split(':')[:3] if value else []
            value = ':'.join(paths) + '...' if len(value.split(':')) > 3 else value
        
        status = "✓" if value else "not set"
        print(f"  {var}: {value if value else status}")
    
    # ==========================================================================
    # RECOMMENDATIONS
    # ==========================================================================
    print_header("RECOMMENDATIONS")
    
    issues = []
    
    if not is_project_venv:
        issues.append("Use project's virtual environment")
    
    try:
        import ftrack_api
        ftrack_loc = getattr(ftrack_api, '__file__', '')
        if ftrack_loc and '.venv' not in ftrack_loc and 'venv' not in ftrack_loc:
            issues.append("ftrack_api is loaded from system, not venv")
    except ImportError:
        issues.append("ftrack_api is not installed")
    
    if not os.path.exists(venv_dir):
        issues.append("Virtual environment does not exist - run ./setup_environment.sh")
    
    if issues:
        print("\n⚠️  Issues found:")
        for issue in issues:
            print(f"  • {issue}")
        
        print("\n📋 To fix:")
        print(f"  cd {script_dir}")
        if not os.path.exists(venv_dir):
            print("  ./setup_environment.sh")
        print("  ./run_in_venv.sh test_installation.py")
    else:
        print("\n✅ Environment looks good!")
    
    print("\n")
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())

import json
import os
import uuid

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .decorators import creator_required
from .services.excel_parser import parse_file
from .services.excel_template import build_template
from .services.importer import save_import


@creator_required
def index(request):
    return render(request, 'imports/index.html')


@creator_required
@require_http_methods(['GET'])
def download_template(request):
    buffer = build_template()
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="easybiodiv_template.xlsx"'
    return response


@creator_required
@require_http_methods(['POST'])
def upload(request):
    if 'excel_file' not in request.FILES:
        return render(request, 'imports/index.html', {'error': 'Aucun fichier fourni.'})

    f = request.FILES['excel_file']
    if not f.name.lower().endswith('.xlsx'):
        return render(request, 'imports/index.html', {
            'error': 'Format invalide. Utilisez un fichier .xlsx.',
        })

    parsed = parse_file(f)

    tmp_dir = os.path.join(settings.MEDIA_ROOT, 'imports', 'tmp')
    os.makedirs(tmp_dir, exist_ok=True)
    import_key = str(uuid.uuid4())
    json_path = os.path.join(tmp_dir, f'{import_key}.json')
    with open(json_path, 'w', encoding='utf-8') as fp:
        json.dump({'sheets': parsed}, fp, ensure_ascii=False)

    request.session['import_key'] = import_key
    return redirect('imports:preview')


@creator_required
@require_http_methods(['GET'])
def preview(request):
    import_key = request.session.get('import_key')
    if not import_key:
        return redirect('imports:index')

    json_path = os.path.join(settings.MEDIA_ROOT, 'imports', 'tmp', f'{import_key}.json')
    if not os.path.exists(json_path):
        return redirect('imports:index')

    with open(json_path, encoding='utf-8') as fp:
        data = json.load(fp)

    sheet_summaries = {}
    for sheet_name, rows in data['sheets'].items():
        sheet_summaries[sheet_name] = {
            'rows': rows,
            'ok_count': sum(1 for r in rows if r['status'] == 'ok'),
            'duplicate_count': sum(1 for r in rows if r['status'] == 'duplicate'),
            'error_count': sum(1 for r in rows if r['status'] == 'error'),
        }

    has_importable = any(s['ok_count'] > 0 for s in sheet_summaries.values())
    return render(request, 'imports/preview.html', {
        'sheets': sheet_summaries,
        'has_importable': has_importable,
    })


@creator_required
@require_http_methods(['POST'])
def confirm(request):
    import_key = request.session.get('import_key')
    if not import_key:
        return redirect('imports:index')

    json_path = os.path.join(settings.MEDIA_ROOT, 'imports', 'tmp', f'{import_key}.json')
    if not os.path.exists(json_path):
        return redirect('imports:index')

    with open(json_path, encoding='utf-8') as fp:
        data = json.load(fp)

    counts = save_import(data['sheets'])

    os.unlink(json_path)
    del request.session['import_key']

    total = sum(counts.values())
    return render(request, 'imports/index.html', {
        'success': f"{total} enregistrement(s) importé(s) avec succès.",
        'counts': counts,
    })

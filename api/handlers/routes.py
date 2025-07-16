import os
from tempfile import NamedTemporaryFile

from flask import Blueprint, flash, redirect, render_template, request

from ..modules.database import insert_record, get_history
from ..modules.pptx_utils import extract_pptx

routes = Blueprint('routes', __name__)


@routes.route('/', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        if 'pptx' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['pptx']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        slide_start = int(request.form.get('start', 31))
        slide_end = int(request.form.get('end', 32))
        with NamedTemporaryFile(delete=False, suffix='.pptx') as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name
        try:
            kpis, table = extract_pptx(tmp_path, slide_start, slide_end)
            insert_record(file.filename, slide_start, slide_end, kpis, table)
            slides = (slide_start, slide_end)
            return render_template('dashboard.html', kpis=kpis, table=table, slides=slides)
        except Exception as e:
            flash(f'Error processing PPTX: {e}')
            return redirect(request.url)
        finally:
            os.unlink(tmp_path)
    return render_template('upload.html')


@routes.route('/history')
def history():
    history = get_history()
    return render_template('history.html', history=history)

import datetime

from django.utils.translation import get_language
from django.views.generic import TemplateView

from .info import legal_context

# Date de dernière révision des textes, affichée en bas de chaque page.
# À mettre à jour à chaque modification d'un gabarit legal/<langue>/*.html.
TEXTS_UPDATED = datetime.date(2026, 10, 23)


class LegalPageView(TemplateView):
    """Page légale rédigée en entier par langue (legal/fr/, legal/en/).

    Ces textes sont des documents longs : une version par langue se relit et se
    corrige d'un bloc, là où un catalogue gettext les hacherait en dizaines de
    msgids. Seuls le titre et les libellés d'interface passent par gettext.
    """

    template_name = 'legal/page.html'
    page = None
    title = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lang = 'en' if (get_language() or '').startswith('en') else 'fr'
        context.update(
            page=self.page,
            page_title=self.title,
            body_template=f'legal/{lang}/{self.page}.html',
            legal=legal_context(),
            texts_updated=TEXTS_UPDATED,
        )
        return context

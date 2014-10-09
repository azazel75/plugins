# -*- coding: utf-8 -*-
# :Progetto:  nikola -- render json model
# :Creato:    ven 26 set 2014 19:16:40 CEST
# :Autore:    Alberto Berti <alberto@metapensiero.it>
# :Licenza:   GNU General Public License version 3 or later
#


from __future__ import unicode_literals
from nikola.plugin_categories import Task
from nikola.utils import config_changed, LocaleBorg
import nssjson as json
import io

def post_as_dict(self, post, lang=None):
    if lang is None:
        lang = LocaleBorg().current_lang
    result = {
        'meta': post.meta[lang],
        'translated_to': list(post.translated_to),
        'is_draft': post.is_draft,
        'is_private': post.is_private,
        'use_in_feeds': post.use_in_feeds,
        'tags': post._tags[lang],
        'text': post.text(lang),
        'text_stripped': post.text(strip_html=True),
        'text_teaser': None,
        'id': post.permalink() + '.json',
        'template_name': post.template_name,
        'date': post.date,
        'date_formatted': post.date.strftime(
            post.config.GLOBAL_CONTEXT['date_format'])
    }
    if post.config['INDEX_TEASERS']:
        result['text_teaser'] = post.text(teaser_only=True)
    translated_ids = {}
    for l in result['translated_to']:
        translated_ids[l] = post.permalink(lang=l) + '.json'
    result['translated_ids'] = translated_ids
    return result


class RenderPages(Task):
    """Render json model"""

    name = "render_spa"

    def gen_tasks(self):
        """Build final pages from metadata and HTML fragments."""
        kw = {
            "post_pages": self.site.config["post_pages"],
            "translations": self.site.config["TRANSLATIONS"],
            "filters": self.site.config["FILTERS"],
            "show_untranslated_posts": self.site.config['SHOW_UNTRANSLATED_POSTS'],
            "demote_headers": self.site.config['DEMOTE_HEADERS'],
            "index_display_post_count": self.site.config['INDEX_DISPLAY_POST_COUNT'],
            "messages": self.site.MESSAGES,
            "index_teasers": self.site.config['INDEX_TEASERS'],
            "output_folder": self.site.config['OUTPUT_FOLDER'],
            "blog_title": self.site.config['BLOG_TITLE'],
            "content_footer": self.site.config['CONTENT_FOOTER'],
        }

        self.site.scan_posts()
        yield self.group_task()
        for lang in kw["translations"]:
            for post in self.site.timeline:
                if not kw["show_untranslated_posts"] and not post.is_translation_available(lang):
                    continue
                for task in self.site.generic_page_renderer(lang, post,
                                                            kw["filters"]):
                    task['uptodate'] = [config_changed({
                        1: task['uptodate'][0].config,
                        2: kw})]
                    task['basename'] = self.name
                    task['task_dep'] = ['render_posts']
                    yield task

    def compile_json(self, post, path, lang=None):
        with io.open(path, 'w+', encoding='utf-8') as dest:
            data = json.dumps(post.as_dict(lang) , indent=2,
                              iso_datetime=True, ensure_ascii=False,
                              encoding='utf-8')
            # TODO: there are some string in py2 after the encoding,
            # have find a better way to handle this
            dest.write(data)

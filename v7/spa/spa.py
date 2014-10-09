# -*- coding: utf-8 -*-
# :Progetto:  nikola -- render json model
# :Creato:    ven 26 set 2014 19:16:40 CEST
# :Autore:    Alberto Berti <alberto@metapensiero.it>
# :Licenza:   GNU General Public License version 3 or later
#


from __future__ import unicode_literals
import io
import os
from nikola.plugin_categories import Task
from nikola.utils import config_changed, LocaleBorg, makedirs
import nssjson as json

def _id(post, lang):
    return post.permalink(lang) + '.json'

def post_as_dict(post, _link, lang=None):
    if lang is None:
        lang = LocaleBorg().current_lang

    result = {
        'abs_permalink': post.permalink(absolute=True),
        'author': post.author(lang), # it has a fallback
        'date': post.date,
        'formatted_date': post.formatted_date(
            post.config.get(
            'DATE_FORMAT', '%Y-%m-%d %H:%M')),
        'id': _id(post, lang),
        'id_comments': post._base_path,
        'is_draft': post.is_draft,
        'is_mathjax': post.is_mathjax,
        'is_private': post.is_private,
        'iso_date': post.date.isoformat(),
        'meta': post.meta[lang],
        'permalink': post.permalink(lang),
        'sourcelink': post.source_link(lang),
        'template_name': post.template_name,
        'text': post.text(lang),
        'text_stripped': post.text(strip_html=True),
        'text_teaser': None,
        'use_in_feeds': post.use_in_feeds,
    }
    if post.config['INDEX_TEASERS']:
        result['text_teaser'] = post.text(teaser_only=True)
    translated_to = []
    for t in post.translations.keys():
        if t != lang and post.is_translation_available(t):
            link = post.permalink(lang=t)
            translated_to.append({
                'lang': t,
                'permalink': link,
                'id': link + '.json'
            })
    result['translated_to'] = translated_to
    for key in ('prev_post', 'next_post'):
        p = getattr(post, key, None)
        if p:
            result[key] = {
                'title': p.title(lang),
                'permalink': p.permalink(lang),
                'id': _id(post, lang)
            }
        else:
            result[key] = None
    if post.use_in_feeds:
        result['enable_comments'] = True
    else:
        result['enable_comments'] = post.config['COMMENTS_IN_STORIES']
    tags = []
    for t in  post._tags[lang]:
        link = _link('tag', t, lang)
        tags.append({'name': t, 'link': link, 'id': link + '.json'})
    result['tags'] = tags
    return result


class RenderSPA(Task):
    """Render json model"""

    name = "render_spa"


    def set_site(self, site):
        super(RenderSPA, self).set_site(site)
        site.GLOBAL_CONTEXT['get_post_data'] = post_as_dict

    def gen_tasks(self):
        """Build final pages from metadata and HTML fragments."""
        kw = {
            "blog_title": self.site.config['BLOG_TITLE'],
            "content_footer": self.site.config['CONTENT_FOOTER'],
            "demote_headers": self.site.config['DEMOTE_HEADERS'],
            "filters": self.site.config["FILTERS"],
            "index_display_post_count": self.site.config['INDEX_DISPLAY_POST_COUNT'],
            "index_teasers": self.site.config['INDEX_TEASERS'],
            "messages": self.site.MESSAGES,
            "output_folder": self.site.config['OUTPUT_FOLDER'],
            "post_pages": self.site.config["post_pages"],
            "show_untranslated_posts": self.site.config['SHOW_UNTRANSLATED_POSTS'],
            "translations": self.site.config["TRANSLATIONS"],
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

    def compile_json(self, path, extractor=None, *args):
        makedirs(os.path.dirname(path))
        with io.open(path, 'w+', encoding='utf-8') as dest:
            if callable(extractor) and args:
                extracted = extractor(*args)
            else:
                extracted = extractor
            data = json.dumps(extracted, indent=2,
                              iso_datetime=True, ensure_ascii=False,
                              encoding='utf-8')
            # TODO: there are some string in py2 after the encoding,
            # have find a better way to handle this
            dest.write(data)

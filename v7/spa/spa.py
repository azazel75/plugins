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
from nikola.utils import config_changed, LocaleBorg, makedirs, copy_file
import lxml
import nssjson as json

def _id(post, lang):
    return post.permalink(lang) + '.json'


def site_context(site):
    from nikola.utils import TranslatableSetting, LOGGER, Functionary
    result = {}
    translated_settings = {}
    for l in site.config['TRANSLATIONS']:
        translated_settings[l] = {}
    for k, v in site.GLOBAL_CONTEXT.items():
        if k in ['template_hooks', 'get_post_data', 'timezone']:
            continue
        if callable(v):
            if isinstance(v, TranslatableSetting):
                for l in site.config['TRANSLATIONS']:
                    translated_settings[l][k] = v.values[l]
                continue
            elif isinstance(v, Functionary):
                # just a callable dict
                pass
            else:
                LOGGER.warn('Found unserializable callable in GLOBAL_CONTEXT: %r, %s' % (k, type(v)))
                continue

        result[k] = v
    result['translated_settings'] = translated_settings
    # TODO: LEGAL_VALUES isn't exported by nikola.py!
    # result['lang'] in LEGAL_VALUES['RTL_LANGUAGES']
    result['is_rtl'] = False
    result['default_lang'] = site.default_lang
    return result

class RenderSPA(Task):
    """Render json model"""

    name = "render_spa"

    def set_site(self, site):
        super(RenderSPA, self).set_site(site)
        site.config['GLOBAL_CONTEXT_FILLER'].append(self.add_spa_data)
        self._cache = {}

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
            "views": [
                'post.partial',
                'post_meta.partial',
                'story.partial',
            ]
        }

        json_subpath = os.path.join('assets', 'json')
        json_base_path = os.path.join(self.site.config['OUTPUT_FOLDER'],
                                 json_subpath)
        view_base_path = os.path.join(self.site.config['OUTPUT_FOLDER'], 'assets',
                                      'view')

        self.site.scan_posts()
        yield self.group_task()
        _link = self.site.link
        for lang in kw["translations"]:
            for post in self.site.timeline:
                if not kw["show_untranslated_posts"] and not post.is_translation_available(lang):
                    continue
                extension = self.site.get_compiler(post.source_path).extension()
                output_name = os.path.join(json_base_path,
                                           post.destination_path(lang, extension) +
                                           '.json')
                task = {
                    'name': os.path.normpath(output_name),
                    'targets': [output_name],
                    'actions': [(self.compile_json, [output_name, self.post_as_dict,
                                                     post, _link, lang])],
                    'clean': True,
                    'uptodate': [config_changed({
                        1: post.text(lang),
                        2: post.title(lang),
                        3: kw
                    })],
                    'task_dep': ['render_posts'],
                    'basename': self.name,
                    'file_dep': post.fragment_deps(lang)
                }
                yield task
        # render globals
        output_name = os.path.join(json_base_path, 'globals.json')
        yield {
            'name': os.path.normpath(output_name),
            'targets': [output_name],
            'actions': [(self.compile_json, [output_name, site_context, self.site])],
            'clean': True,
            'uptodate': [config_changed({
                1: kw
            })],
            'basename': self.name
        }
        # copy views
        template_deps = self.site.template_system.template_deps
        template_to_copy = set()
        for view in kw['views']:
            template_to_copy = template_to_copy.union(template_deps(view))

        for t in template_to_copy:
            output_name = os.path.join(view_base_path, os.path.basename(t))
            yield {
                'name': os.path.normpath(output_name),
                'targets': [output_name],
                'actions': [(copy_file, [t, output_name])],
                'clean': True,
                'file_dep': [t],
                'basename': self.name
            }
        for task in self.list_template_tasks(json_subpath):
            yield task

    def _gen_dependent_json_tasks(self, task_name, json_subpath):
        plugin = self.site.plugin_manager.getPluginByName(task_name, 'Task')\
                 .plugin_object
        gen =  plugin.gen_tasks()
        # ignore first item which is a group_task
        gen.next()
        from doit.tools import set_trace; set_trace()
        for in_task in gen:
            file_dep = in_task['targets'][0]
            out_target_parts = file_dep.split(os.sep)
            out_target_parts.insert(1, json_subpath)
            out_target_parts[-1] += '.json'
            output_name = os.path.join(*out_target_parts)
            yield output_name, in_task, {
                'name': os.path.normpath(output_name),
                'targets': [output_name],
                'clean': True,
                'file_dep': [file_dep],
                'basename': self.name
            }

    def list_template_tasks(self, json_subpath):
        "Tasks which use the list.tmpl for render"
        # indexes
        for plugin in ('render_indexes', 'render_archive'):
            for output_name, in_task, task in \
                self._gen_dependent_json_tasks(plugin, json_subpath):
                context = in_task['actions'][0][1][2]
                post_dicts = [self.post_as_dict(post, self.site.link,
                                                context['lang'])\
                              for post in context['posts']]
                context['posts'] = post_dicts
                context['template_name'] = 'list.tmpl'
                task['actions'] = [(self.compile_json, [output_name, context])]
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

    def add_spa_data(self, context, template_name):
        post = context.get('post')
        if post and ('post' in template_name or 'story' in template_name):
            post = self.post_as_dict(post, context['_link'], context.get('lang'))
            context['post'] = post
            context['post_json'] = json.dumps(post, iso_datetime=True, ensure_ascii=False)
            context['globals_json'] = json.dumps(site_context(self.site), ensure_ascii=False)

    def post_as_dict(self, post, _link, lang=None):
        if lang is None:
            lang = LocaleBorg().current_lang

        result = self._cache.get((post, lang))
        if result:
            return result
        # replace  link:// stuff in the html
        extension = self.site.get_compiler(post.source_path).extension()
        url_part = post.destination_path(lang, extension)
        src = os.sep + url_part
        src = os.path.normpath(src)
        src = "/".join(src.split(os.sep))
        post_text = post.text(lang)
        frags = lxml.html.fragments_fromstring(post_text)
        post_text = ''
        for frag in frags:
            frag.rewrite_links(lambda dst: self.site.url_replacer(src, dst, lang))
            post_text += lxml.html.tostring(frag, encoding='unicode', method='html', pretty_print=False)

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
            'text': post_text,
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
        self._cache[(post, lang)] = result
        return result

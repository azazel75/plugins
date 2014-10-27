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


class RenderSPA(Task):
    """Render json model"""

    name = "render_spa"

    def set_site(self, site):
        super(RenderSPA, self).set_site(site)
        site.config['GLOBAL_CONTEXT_FILLER'].append(self.fill_context_spa)
        self._cache = {}
        self._context_fill_config = {
            'gallery.tmpl': self._fill_gallery_context,
            'index.tmpl': self._fill_index_context,
            'list.tmpl': self._fill_list_context,
            'post.tmpl': self._fill_post_context,
            'story.tmpl': self._fill_post_context,
        }

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
                'gallery.partial',
                'gallery_meta.partial',
                'gallery_extra_js.partial',
                'index.partial',
                'list.partial'
            ],
            'client_templates': {
                'gallery.tmpl': {
                    'view-content': 'gallery.partial',
                    'view-extrajs': 'gallery_extra_js.partial',
                    'view-meta': 'gallery_meta.partial',
                    'view-sourcelink': None
                },
                'index.tmpl': {
                    'view-content': 'index.partial',
                    'view-extrajs': None,
                    'view-meta': None,
                    'view-sourcelink': None
                },
                'list.tmpl': {
                    'view-content': 'list.partial',
                    'view-extrajs': None,
                    'view-meta': None,
                    'view-sourcelink': None
                },
                'post.tmpl': {
                    'view-content': 'post.partial',
                    'view-extrajs': None,
                    'view-meta': 'post_meta.partial',
                    'view-sourcelink': 'post_sourcelink.partial'
                },
                'story.tmpl': {
                    'view-content': 'story.partial',
                    'view-extrajs': None,
                    'view-meta': 'post_meta.partial',
                    'view-sourcelink': 'post_sourcelink.partial'
                },
            }

        }

        json_subpath = os.path.join('assets', 'json')
        json_base_path = os.path.join(self.site.config['OUTPUT_FOLDER'],
                                 json_subpath)
        view_base_path = os.path.join(self.site.config['OUTPUT_FOLDER'], 'assets',
                                      'view')

        self.site.scan_posts()
        yield self.group_task()

        # render globals
        output_name = os.path.join(json_base_path, 'globals.json')
        yield {
            'name': os.path.normpath(output_name),
            'targets': [output_name],
            'actions': [(self.compile_json, [output_name, self.site_context,
                                             self.site, kw['client_templates']])],
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
        for task in self.gallery_template_tasks(json_subpath):
            yield task
        for task in self.post_story_template_tasks(json_subpath):
            yield task
        for task in self.index_template_tasks(json_subpath):
            yield task

    def _gen_dependent_json_tasks(self, task_name, json_subpath, check_fn=None):
        plugin = self.site.plugin_manager.getPluginByName(task_name, 'Task')\
                 .plugin_object
        output_folder_parts = self.site.config['OUTPUT_FOLDER'].split(os.sep)
        gen =  plugin.gen_tasks()
        # ignore first item which is a group_task
        gen.next()
        for in_task in gen:
            if check_fn and not check_fn(plugin, in_task):
                continue
            file_dep = in_task['targets'][0]
            out_target_parts = file_dep.split(os.sep)
            out_target_parts[-1] += '.json'
            # assume that output name has been joined to OUTPUT_FOLDER
            id_parts = out_target_parts[len(output_folder_parts):]
            id = os.path.join(*id_parts)
            out_target_parts.insert(len(output_folder_parts), json_subpath)
            output_name = os.path.join(*out_target_parts)

            yield plugin, in_task, output_name, id, {
                'name': os.path.normpath(output_name),
                'targets': [output_name],
                'clean': True,
                'file_dep': [file_dep],
                'basename': self.name
            }

    def _fill_list_context(self, context, id=None):
        post_dicts = [self.post_as_dict(post, context['lang'])\
                      for post in context['posts']]
        context['posts'] = post_dicts
        context['template_name'] = 'list.tmpl'
        if id:
            context['id'] = id

    def list_template_tasks(self, json_subpath):
        "Tasks which use the list.tmpl for render"
        for plugin, in_task, output_name, id, task in \
            self._gen_dependent_json_tasks('render_archive', json_subpath):
            context = in_task['actions'][0][1][2]
            task['actions'] = [(self.compile_json, [output_name, context])]
            self._fill_list_context(context, id)
            yield task

    def _fill_gallery_context(self, context, id=None):
        context['template_name'] = 'gallery.tmpl'
        post = context['post']
        if post:
            context['post'] = self.post_as_dict(post, context['lang'])
        if id:
            context['id'] = id


    def gallery_template_tasks(self, json_subpath):
        "Tasks which use gallery.tmpl for render"
        def is_valid_task(plugin, task):
            # it's strange, 'action is plugin.render_gallery_index' is False
            # here... maybe something with yapsy?
            action = task['actions'][0][0]
            return hasattr(action, 'im_func') and action.im_func \
                is plugin.render_gallery_index.im_func

        for plugin, in_task, output_name, id, task in \
                self._gen_dependent_json_tasks('render_galleries',
                                               json_subpath,
                                               is_valid_task):
            context = in_task['actions'][0][1][2]
            self._fill_gallery_context(context, id)
            task['actions'] = [(self.compile_json, [output_name, context])]
            yield task


    def _fill_post_context(self, context, id=None):
        post = context['post']
        lang = context['lang']
        context.update({
            'post': self.post_as_dict(post, lang),
            'template_name': post.template_name
        })
        if id:
            context['id'] = id

    def post_story_template_tasks(self, json_subpath):
        "Task which use post.tmpl or story.tmpl"
        for plugin, in_task, output_name, id, task in \
                self._gen_dependent_json_tasks('render_pages',
                                               json_subpath):
            context = in_task['actions'][0][1][2]
            self._fill_post_context(context, id)
            task['actions'] = [(self.compile_json, [output_name, context])]
            yield task

    def _fill_index_context(self, context, id=None):
        post_dicts = [self.post_as_dict(post, context['lang'])\
                      for post in context['posts']]
        context['posts'] = post_dicts
        context['template_name'] = 'index.tmpl'
        context['is_mathjax'] = any(p['is_mathjax'] for p in context['posts'])
        if id:
            context['id'] = id

    def index_template_tasks(self, json_subpath):
        "Tasks which use the index.tmpl for render"
        for plugin, in_task, output_name, id, task in \
            self._gen_dependent_json_tasks('render_indexes', json_subpath):
            context = in_task['actions'][0][1][2]
            task['actions'] = [(self.compile_json, [output_name, context])]
            self._fill_index_context(context, id)
            yield task

    def compile_json(self, path, extractor=None, *args):
        makedirs(os.path.dirname(path))
        with io.open(path, 'w+', encoding='utf-8') as dest:
            if callable(extractor) and args:
                extracted = extractor(*args)
            else:
                extracted = extractor
            data = json.dumps(extracted, iso_datetime=True, ensure_ascii=False,
                              encoding='utf-8')
            # TODO: there are some string in py2 after the encoding,
            # have find a better way to handle this
            dest.write(data)

    def fill_context_spa(self, context, template_name):
        if template_name in self._context_fill_config:
            self._context_fill_config[template_name](context)

    def post_template_data(self, post, lang=None, additional_data=None):
        result = {
            'id': _id(post, lang),
            'lang': lang,
            'post': self.post_as_dict(self, post, lang),
            'template_name': post.template_name
        }

        if additional_data and isinstance(additional_data, dict):
            result.update(additional_data)
        return result

    def post_as_dict(self, post, lang=None):
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
            'id_comments': post._base_path,
            'is_draft': post.is_draft,
            'is_mathjax': post.is_mathjax,
            'is_private': post.is_private,
            'iso_date': post.date.isoformat(),
            'meta': post.meta[lang],
            'permalink': post.permalink(lang),
            'sourcelink': post.source_link(lang),
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
            link = self.site.link('tag', t, lang)
            tags.append({'name': t, 'link': link, 'id': link + '.json'})
        result['tags'] = tags
        self._cache[(post, lang)] = result
        return result

    def site_context(self, site, client_templates):
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
        result['BASE_URL'] = site.config['BASE_URL']
        result['client_templates'] = client_templates
        return result

/*
    Copyright (C) 2017 Google Inc.
    Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
*/

import {
  initWidgets,
} from '../../plugins/utils/current-page-utils';
import '../../controllers/dashboard_controller';
import {RouterConfig} from '../../router';
import routes from './routes';

const $area = $('.area').first();
const sortByNameEmail = list => {
  return new list.constructor(can.makeArray(list).sort(function (a, b) {
    a = a.person || a;
    b = b.person || b;
    a = (can.trim(a.name) || can.trim(a.email)).toLowerCase();
    b = (can.trim(b.name) || can.trim(b.email)).toLowerCase();
    if (a > b) {
      return 1;
    }
    if (a < b) {
      return -1;
    }
    return 0;
  }));
};

RouterConfig.setupRoutes(routes);

const adminListDescriptors = {
  people: {
    model: CMS.Models.Person,
    roles: new can.List(),
    init: function () {
      var self = this;
      CMS.Models.Role
        .findAll({scope__in: 'System,Admin'})
        .done(function (roles) {
          self.roles.replace(sortByNameEmail(roles));
        });
    },
    object_display: 'People',
    tooltip_view: '/static/mustache/people/object_tooltip.mustache',
    header_view:
    // includes only the filter, not the column headers
      '/static/mustache/people/filters.mustache',
    list_view: '/static/mustache/people/object_list.mustache',
    draw_children: true,
    fetch_post_process: sortByNameEmail
  },
  roles: {
    model: CMS.Models.Role,
    extra_params: {scope__in: 'System,Admin,Private Program,Workflow'},
    object_category: 'governance',
    object_display: 'Roles',
    list_view: '/static/mustache/roles/object_list.mustache',
    fetch_post_process: sortByNameEmail
  },
  events: {
    model: CMS.Models.Event,
    object_category: 'governance',
    object_display: 'Events',
    list_view: '/static/mustache/events/object_list.mustache'
  },
  custom_attributes: {
    parent_instance: CMS.Models.CustomAttributable,
    model: CMS.Models.CustomAttributable,
    header_view:
    GGRC.mustache_path +
    '/custom_attribute_definitions/tree_header.mustache',
    show_view:
    GGRC.mustache_path + '/custom_attribute_definitions/tree.mustache',
    sortable: false,
    list_loader: function () {
      return CMS.Models.CustomAttributable.findAll();
    },
    draw_children: true,
    child_options: [{
      model: CMS.Models.CustomAttributeDefinition,
      mapping: 'custom_attribute_definitions',
      show_view:
      GGRC.mustache_path +
      '/custom_attribute_definitions/subtree.mustache',
      footer_view: null,
      add_item_view: null
    }]
  },
  custom_roles: {
    parent_instance: CMS.Models.Roleable,
    model: CMS.Models.Roleable,
    header_view:
    GGRC.mustache_path + '/access_control_roles/tree_header.mustache',
    show_view:
    GGRC.mustache_path + '/access_control_roles/tree.mustache',
    sortable: false,
    list_loader: function () {
      return CMS.Models.Roleable.findAll();
    },
    draw_children: true,
    child_options: [{
      model: CMS.Models.AccessControlRole,
      mapping: 'access_control_roles',
      show_view:
      GGRC.mustache_path + '/access_control_roles/subtree.mustache',
      footer_view: null,
      add_item_view: null
    }]
  }
};

new GGRC.WidgetList('ggrc_admin', {
  admin: {
    people: {
      model: CMS.Models.Person,
      content_controller: GGRC.Controllers.ListView,
      content_controller_options: adminListDescriptors.people,
      widget_id: 'people_list',
      widget_icon: 'person',
      show_filter: false,
      widget_name: function () {
        return 'People';
      },
      widget_info: function () {
        return '';
      }
    },
    roles: {
      model: CMS.Models.Role,
      content_controller: GGRC.Controllers.ListView,
      content_controller_options: adminListDescriptors.roles,
      widget_id: 'roles_list',
      widget_icon: 'role',
      show_filter: false,
      widget_name: function () {
        return 'Roles';
      },
      widget_info: function () {
        return '';
      }
    },
    events: {
      model: CMS.Models.Event,
      content_controller: GGRC.Controllers.ListView,
      content_controller_options: adminListDescriptors.events,
      widget_id: 'events_list',
      widget_icon: 'event',
      widget_name: function () {
        return 'Events';
      },
      widget_info: function () {
        return '';
      }
    },
    custom_attributes: {
      widget_id: 'custom_attribute',
      widget_name: 'Custom Attributes',
      widget_icon: 'workflow',
      content_controller: CMS.Controllers.TreeView,
      content_controller_selector: 'ul',
      model: CMS.Models.CustomAttributable,
      widget_initial_content:
      '<ul' +
      '  class="tree-structure new-tree colored-list"' +
      '  data-no-pin="true"' +
      '></ul>',
      content_controller_options: adminListDescriptors.custom_attributes
    },
    custom_roles: {
      widget_id: 'custom_roles',
      widget_name: 'Custom Roles',
      widget_icon: 'unlock',
      content_controller: CMS.Controllers.TreeView,
      content_controller_selector: 'ul',
      content_controller_options: adminListDescriptors.custom_roles,
      model: CMS.Models.Roleable,
      widget_initial_content: [
        '<ul',
        '  class="tree-structure new-tree colored-list"',
        '  data-no-pin="true"',
        '></ul>'
      ].join('\n')
    }
  }
});

$area.cms_controllers_dashboard({
  widget_descriptors: GGRC.WidgetList.get_widget_list_for('admin'),
  menu_tree_spec: GGRC.admin_menu_spec,
  default_widgets: [
    'people', 'roles', 'events', 'custom_attributes', 'custom_roles'
  ]
});
initWidgets();

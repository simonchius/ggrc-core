/*!
 Copyright (C) 2017 Google Inc.
 Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
 */

import template from './checkbox-form-field-view.mustache';

(function (can, GGRC) {
  'use strict';

  GGRC.Components('checkboxFormFieldView', {
    tag: 'checkbox-form-field-view',
    template: template,
    viewModel: {
      value: null,
      disabled: false
    }
  });
})(window.can, window.GGRC);

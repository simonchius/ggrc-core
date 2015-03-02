# Copyright (C) 2013 Google Inc., authors, and contributors <see AUTHORS file>
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
# Created By: dan@reciprocitylabs.com
# Maintained By: vraj@reciprocitylabs.com

import factory
import random
from ggrc import db
from ggrc.models import *

def random_string(prefix=''):
  return '{prefix}{suffix}'.format(
      prefix=prefix,
      suffix=random.randint(0,9999999999),
      )

class ModelFactory(factory.Factory):
  #modified_by_id = 1

  @classmethod
  def _create(cls, target_class, *args, **kwargs):
    instance = target_class(*args, **kwargs)
    db.session.add(instance)
    db.session.commit()
    return instance

class SlugFactory(factory.Factory):
  slug = factory.LazyAttribute(lambda m: random_string('slug'))
  title = factory.LazyAttribute(lambda m: random_string('title'))

class DirectiveFactory(ModelFactory):
  class Meta:
    model = Directive

  title = factory.LazyAttribute(lambda m: random_string('title'))

class ControlFactory(ModelFactory, SlugFactory):
  class Meta:
    model = Control

  directive = factory.SubFactory(DirectiveFactory)
  kind_id = None
  version = None
  documentation_description = None
  verify_frequency_id = None
  fraud_related = None
  key_control = None
  active = None
  notes = None

class ControlCategoryFactory(ModelFactory):
  class Meta:
    model = ControlCategory

  name = factory.LazyAttribute(lambda m: random_string('name'))
  lft = None
  rgt = None
  scope_id = None
  depth = None
  required = None

class CategorizationFactory(ModelFactory):
  class Meta:
    model = Categorization

  category = None
  categorizable = None
  category_id = None
  categorizable_id = None
  categorizable_type = None

class ProgramFactory(ModelFactory):
  class Meta:
    model = Program

  title = 'program_title'
  slug = 'program_slug'

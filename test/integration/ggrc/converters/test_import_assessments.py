# Copyright (C) 2017 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

# pylint: disable=maybe-no-member, invalid-name

"""Test request import and updates."""

import datetime
from collections import OrderedDict

import ddt
import freezegun

from ggrc import db
from ggrc import models
from ggrc.access_control.role import get_custom_roles_for
from ggrc.converters import errors

from integration.ggrc import TestCase
from integration.ggrc.generator import ObjectGenerator
from integration.ggrc.models import factories


@ddt.ddt
class TestAssessmentImport(TestCase):
  """Basic Assessment import tests with.

  This test suite should test new Assessment imports, exports, and updates.
  The main focus of these tests is checking error messages for invalid state
  transitions.
  """

  def setUp(self):
    """Set up for Assessment test cases."""
    super(TestAssessmentImport, self).setUp()
    self.client.get("/login")

  def test_import_assessments_with_templates(self):
    """Test importing of assessments with templates."""

    self.import_file("assessment_template_no_warnings.csv")
    response = self.import_file("assessment_with_templates.csv")
    self._check_csv_response(response, {})

    assessment = models.Assessment.query.filter(
        models.Assessment.slug == "A 4").first()

    values = set(v.attribute_value for v in assessment.custom_attribute_values)
    self.assertIn("abc", values)
    self.assertIn("2015-07-15", values)

  def _test_assessment_users(self, asmt, users):
    """ Test that all users have correct roles on specified Assessment"""
    verification_errors = ""
    ac_roles = {
        acr_name: acr_id
        for acr_id, acr_name in get_custom_roles_for(asmt.type).items()
    }
    for user_name, expected_types in users.items():
      for role in expected_types:
        try:
          user = models.Person.query.filter_by(name=user_name).first()
          acl_len = models.AccessControlList.query.filter_by(
              ac_role_id=ac_roles[role],
              person_id=user.id,
              object_id=asmt.id,
              object_type=asmt.type,
          ).count()
          self.assertEqual(
              acl_len, 1,
              "User {} is not mapped to {}".format(user.email, asmt.slug)
          )
        except AssertionError as error:
          verification_errors += "\n\nChecks for Users-Assessment mapping "\
              "failed for user '{}' with:\n{}".format(user_name, str(error))

    self.assertEqual(verification_errors, "", verification_errors)

  def _test_assigned_user(self, assessment, user_id, role):
    acls = models.AccessControlList.query.filter_by(
        person_id=user_id,
        object_id=assessment.id,
        object_type=assessment.type,
    )
    self.assertEqual(
        [user_id] if user_id else [],
        [i.person_id for i in acls if i.ac_role.name == role]
    )

  def test_assessment_full_no_warnings(self):
    """ Test full assessment import with no warnings

    CSV sheet:
      https://docs.google.com/spreadsheets/d/1Jg8jum2eQfvR3kZNVYbVKizWIGZXvfqv3yQpo2rIiD8/edit#gid=704933240&vpid=A7
    """
    response = self.import_file("assessment_full_no_warnings.csv")
    self._check_csv_response(response, {})

    # Test first Assessment line in the CSV file
    asmt_1 = models.Assessment.query.filter_by(slug="Assessment 1").first()
    users = {
        "user 1": {"Assignees"},
        "user 2": {"Assignees", "Creators"}
    }
    self._test_assessment_users(asmt_1, users)
    self.assertEqual(asmt_1.status, models.Assessment.START_STATE)

    # Test second Assessment line in the CSV file
    asmt_2 = models.Assessment.query.filter_by(slug="Assessment 2").first()
    users = {
        "user 1": {"Assignees"},
        "user 2": {"Creators"},
        "user 3": {},
        "user 4": {},
        "user 5": {},
    }
    self._test_assessment_users(asmt_2, users)
    self.assertEqual(asmt_2.status, models.Assessment.PROGRESS_STATE)

    audit = [obj for obj in asmt_1.related_objects() if obj.type == "Audit"][0]
    self.assertEqual(audit.context, asmt_1.context)

    evidence = models.Document.query.filter_by(title="some title 2").first()
    self.assertEqual(audit.context, evidence.context)

  def test_assessment_import_states(self):
    """ Test Assessment state imports

    These tests are an intermediate part for zucchini release and will be
    updated in the next release.

    CSV sheet:
      https://docs.google.com/spreadsheets/d/1Jg8jum2eQfvR3kZNVYbVKizWIGZXvfqv3yQpo2rIiD8/edit#gid=299569476
    """
    self.import_file("assessment_full_no_warnings.csv")
    response = self.import_file("assessment_update_intermediate.csv")
    expected_errors = {
        "Assessment": {
            "block_errors": set(),
            "block_warnings": set(),
            "row_errors": set(),
            "row_warnings": set(),
        }
    }
    self._check_csv_response(response, expected_errors)

    assessments = {r.slug: r for r in models.Assessment.query.all()}
    self.assertEqual(assessments["Assessment 60"].status,
                     models.Assessment.START_STATE)
    self.assertEqual(assessments["Assessment 61"].status,
                     models.Assessment.PROGRESS_STATE)
    self.assertEqual(assessments["Assessment 62"].status,
                     models.Assessment.DONE_STATE)
    self.assertEqual(assessments["Assessment 63"].status,
                     models.Assessment.FINAL_STATE)
    self.assertEqual(assessments["Assessment 64"].status,
                     models.Assessment.FINAL_STATE)
    self.assertEqual(assessments["Assessment 3"].status,
                     models.Assessment.FINAL_STATE)
    self.assertEqual(assessments["Assessment 4"].status,
                     models.Assessment.FINAL_STATE)

    # Check that there is only one attachment left
    asmt1 = assessments["Assessment 1"]
    self.assertEqual({"a.b.com", "c d com"},
                     {i.title for i in asmt1.document_url})
    self.assertEqual({u'evidence title 1'},
                     {i.title for i in asmt1.document_evidence})

  @ddt.data(
      (True, True),
      (False, False),
  )
  @ddt.unpack
  def test_error_ca_import_states(self, dry_run, has_error):
    """Test changing state of Assessment with unfilled mandatory CA"""
    with factories.single_commit():
      audit = factories.AuditFactory()
      asmnt = factories.AssessmentFactory(audit=audit)
      factories.CustomAttributeDefinitionFactory(
          title="def1",
          definition_type="assessment",
          definition_id=asmnt.id,
          attribute_type="Date",
          mandatory=True,
      )
    response = self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", asmnt.slug),
        ("Audit", audit.slug),
        ("Assignees", "user@example.com"),
        ("Creators", "user@example.com"),
        ("Title", "Test title"),
        ("State", "Completed"),
    ]), dry_run=dry_run)
    expected_errors = {
        "Assessment": {
            "row_errors": {
                errors.VALIDATION_ERROR.format(
                    line=3,
                    column_name="State",
                    message="CA-introduced completion preconditions are not "
                            "satisfied. Check preconditions_failed of items "
                            "of self.custom_attribute_values"
                )
            }
        }
    }
    self._check_csv_response(response, expected_errors if has_error else {})

  def test_assessment_warnings_errors(self):
    """ Test full assessment import with warnings and errors

    CSV sheet:
      https://docs.google.com/spreadsheets/d/1Jg8jum2eQfvR3kZNVYbVKizWIGZXvfqv3yQpo2rIiD8/edit#gid=889865936
    """
    self.import_file("assessment_full_no_warnings.csv")
    response = self.import_file("assessment_with_warnings_and_errors.csv")

    expected_errors = {
        "Assessment": {
            "block_errors": set([]),
            "block_warnings": {
                errors.UNKNOWN_COLUMN.format(
                    line=2,
                    column_name="error description - non existing column will "
                    "be ignored"
                ),
                errors.UNKNOWN_COLUMN.format(
                    line=2,
                    column_name="actual error message"
                ),
                errors.UNKNOWN_COLUMN.format(
                    line=2,
                    column_name="map:project"
                ),
            },
            "row_errors": {
                errors.MISSING_VALUE_ERROR.format(
                    line=19,
                    column_name="Audit"
                ),
                errors.DUPLICATE_VALUE_IN_CSV.format(
                    line_list="20, 22",
                    column_name="Code",
                    value="Assessment 22",
                    s="",
                    ignore_lines="22",
                ),
            },
            "row_warnings": {
                errors.UNKNOWN_OBJECT.format(
                    line=19,
                    object_type="Audit",
                    slug="not existing"
                ),
                errors.WRONG_VALUE_DEFAULT.format(
                    line=20,
                    column_name="State",
                    value="open",
                ),
            },
        }
    }
    self._check_csv_response(response, expected_errors)

  def test_mapping_control_through_snapshot(self):
    "Test for add mapping control on assessment"
    with factories.single_commit():
      audit = factories.AuditFactory()
      assessment = factories.AssessmentFactory(audit=audit)
      factories.RelationshipFactory(source=audit, destination=assessment)
      control = factories.ControlFactory()
    revision = models.Revision.query.filter(
        models.Revision.resource_id == control.id,
        models.Revision.resource_type == control.__class__.__name__
    ).order_by(
        models.Revision.id.desc()
    ).first()
    factories.SnapshotFactory(
        parent=audit,
        child_id=control.id,
        child_type=control.__class__.__name__,
        revision_id=revision.id
    )
    db.session.commit()
    self.assertFalse(db.session.query(
        models.Relationship.get_related_query(
            assessment, models.Snapshot()
        ).exists()).first()[0])
    self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", assessment.slug),
        ("map:Control versions", control.slug),
    ]))
    self.assertTrue(db.session.query(
        models.Relationship.get_related_query(
            assessment, models.Snapshot()
        ).exists()).first()[0])

  @ddt.data(
      ("yes", True),
      ("no", True),
      ("invalid_data", False),
  )
  @ddt.unpack
  def test_import_view_only_field(self, value, is_valid):
    "Test import view only fields"
    with factories.single_commit():
      audit = factories.AuditFactory()
      assessment = factories.AssessmentFactory(audit=audit)
      factories.RelationshipFactory(source=audit, destination=assessment)
    resp = self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", assessment.slug),
        ("archived", value),
    ]))
    row_warnings = []
    if not is_valid:
      row_warnings.append(u"Line 3: Field 'Archived' contains invalid data. "
                          u"The value will be ignored.")
    self.assertEqual(
        [{
            u'ignored': 0,
            u'updated': 1,
            u'block_errors': [],
            u'name': u'Assessment',
            u'created': 0,
            u'deleted': 0,
            u'deprecated': 0,
            u'row_warnings': row_warnings,
            u'rows': 1,
            u'block_warnings': [],
            u'row_errors': [],
        }],
        resp)

  @ddt.data((False, "no", 0, 1, []),
            (True, "yes", 1, 0, [u'Line 3: Importing archived instance is '
                                 u'prohibited. The line will be ignored.']))
  @ddt.unpack
  # pylint: disable=too-many-arguments
  def test_import_archived_assessment(self, is_archived, value, ignored,
                                      updated, row_errors):
    """Test archived assessment import procedure"""
    with factories.single_commit():
      audit = factories.AuditFactory(archived=is_archived)
      assessment = factories.AssessmentFactory(audit=audit)
      factories.RelationshipFactory(source=audit, destination=assessment)
    resp = self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", assessment.slug),
        ("archived", value),
        ("description", "archived assessment description")
    ]))
    self.assertEqual([{
        u'ignored': ignored,
        u'updated': updated,
        u'block_errors': [],
        u'name': u'Assessment',
        u'created': 0,
        u'deleted': 0,
        u'deprecated': 0,
        u'row_warnings': [],
        u'rows': 1,
        u'block_warnings': [],
        u'row_errors': row_errors
    }], resp)

  def test_create_new_assessment_with_mapped_control(self):
    "Test for creation assessment with mapped controls"
    with factories.single_commit():
      audit = factories.AuditFactory()
      control = factories.ControlFactory()
    revision = models.Revision.query.filter(
        models.Revision.resource_id == control.id,
        models.Revision.resource_type == control.__class__.__name__
    ).order_by(
        models.Revision.id.desc()
    ).first()
    factories.SnapshotFactory(
        parent=audit,
        child_id=control.id,
        child_type=control.__class__.__name__,
        revision_id=revision.id
    )
    db.session.commit()
    self.assertFalse(db.session.query(
        models.Relationship.get_related_query(
            models.Assessment(), models.Snapshot()
        ).exists()).first()[0])
    slug = "TestAssessment"
    response = self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", slug),
        ("Audit*", audit.slug),
        ("Assignees*", models.Person.query.all()[0].email),
        ("Creators", models.Person.query.all()[0].email),
        ("Title", "Strange title"),
        ("map:Control versions", control.slug),
    ]))
    self._check_csv_response(response, {})
    assessment = models.Assessment.query.filter(
        models.Assessment.slug == slug
    ).first()
    self.assertTrue(db.session.query(models.Relationship.get_related_query(
        assessment, models.Snapshot()).exists()).first()[0]
    )

  def test_create_import_assignee(self):
    "Test for creation assessment with mapped assignees"
    name = "test_name"
    email = "test@email.com"
    slug = "TestAssessment"
    with factories.single_commit():
      audit = factories.AuditFactory()
      assignee_id = factories.PersonFactory(name=name, email=email).id
    self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", slug),
        ("Audit*", audit.slug),
        ("Assignees*", email),
        ("Creators", models.Person.query.all()[0].email),
        ("Title", "Strange title"),
    ]))
    assessment = models.Assessment.query.filter(
        models.Assessment.slug == slug
    ).first()
    self._test_assigned_user(assessment, assignee_id, "Assignees")

  def test_create_import_creators(self):
    "Test for creation assessment with mapped creator"
    name = "test_name"
    email = "test@email.com"
    slug = "TestAssessment"
    with factories.single_commit():
      audit = factories.AuditFactory()
      creator_id = factories.PersonFactory(name=name, email=email).id
    self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", slug),
        ("Audit*", audit.slug),
        ("Assignees*", models.Person.query.all()[0].email),
        ("Creators", email),
        ("Title", "Strange title"),
    ]))
    assessment = models.Assessment.query.filter(
        models.Assessment.slug == slug
    ).first()
    self._test_assigned_user(assessment, creator_id, "Creators")

  def test_update_import_creators(self):
    "Test for creation assessment with mapped creator"
    slug = "TestAssessment"
    name = "test_name"
    email = "test@email.com"
    with factories.single_commit():
      assessment = factories.AssessmentFactory(slug=slug)
      creator_id = factories.PersonFactory(name=name, email=email).id
    self._test_assigned_user(assessment, None, "Creators")
    self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", slug),
        ("Creators", email),
    ]))
    assessment = models.Assessment.query.filter(
        models.Assessment.slug == slug
    ).first()
    self._test_assigned_user(assessment, creator_id, "Creators")

  def test_update_import_assignee(self):
    "Test for creation assessment with mapped creator"
    slug = "TestAssessment"
    name = "test_name"
    email = "test@email.com"
    with factories.single_commit():
      assessment = factories.AssessmentFactory(slug=slug)
      assignee_id = factories.PersonFactory(name=name, email=email).id
    self._test_assigned_user(assessment, None, "Assignees")
    self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", slug),
        ("Assignees", email),
    ]))
    assessment = models.Assessment.query.filter(
        models.Assessment.slug == slug
    ).first()
    self._test_assigned_user(assessment, assignee_id, "Assignees")

  def test_update_import_verifiers(self):
    """Test import does not delete verifiers if empty value imported"""
    slug = "TestAssessment"
    assessment = factories.AssessmentFactory(slug=slug)

    name = "test_name"
    email = "test@email.com"
    verifier = factories.PersonFactory(name=name, email=email)
    verifier_id = verifier.id

    self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", slug),
        ("Verifiers", email),
    ]))
    assessment = models.Assessment.query.filter(
        models.Assessment.slug == slug
    ).first()
    self._test_assigned_user(assessment, verifier_id, "Verifiers")
    self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", slug),
        ("Verifiers", ""),
    ]))
    assessment = models.Assessment.query.filter(
        models.Assessment.slug == slug
    ).first()
    self._test_assigned_user(assessment, verifier_id, "Verifiers")

  @ddt.data(
      (
          "Last Updated",
          lambda: datetime.date.today() - datetime.timedelta(7),
      ),
      (
          "Created Date",
          lambda: datetime.date.today() - datetime.timedelta(7),
      ),
  )
  @ddt.unpack
  def test_update_non_changeable_field(self, field, value_creator):
    "Test for creation assessment with unchangeable fields"
    slug = "TestAssessment"
    with factories.single_commit():
      value = value_creator()
      factories.AssessmentFactory(
          slug=slug,
          modified_by=factories.PersonFactory(email="modifier@email.com"),
          updated_at=datetime.date.today(),
          created_at=datetime.date.today(),
      )
    data = [{
        "object_name": "Assessment",
        "fields": "all",
        "filters": {
            "expression": {
                "left": "code",
                "op": {"name": "="},
                "right": slug
            },
        }
    }]
    before_update = self.export_parsed_csv(data)["Assessment"][0][field]
    with freezegun.freeze_time("2017-9-10"):
      self.import_data(OrderedDict([("object_type", "Assessment"),
                                    ("Code*", slug),
                                    (field, value)]))
    self.assertEqual(before_update,
                     self.export_parsed_csv(data)["Assessment"][0][field])

  @ddt.data(
      ("Last Updated By", "new_user@email.com"),
  )
  @ddt.unpack
  def test_exportable_only_updated_by(self, field, value):
    """Test exportable only "Last Updated By" field"""
    slug = "TestAssessment"
    with factories.single_commit():
      factories.AssessmentFactory(
          slug=slug,
          modified_by=factories.PersonFactory(email="modifier@email.com"),
      )
    data = [{
        "object_name": "Assessment",
        "fields": "all",
        "filters": {
            "expression": {
                "left": "code",
                "op": {"name": "="},
                "right": slug
            },
        }
    }]
    before_update = self.export_parsed_csv(data)["Assessment"][0][field]
    self.assertEqual(before_update, "modifier@email.com")
    self.import_data(OrderedDict([("object_type", "Assessment"),
                                  ("Code*", slug),
                                  (field, value)]))
    after_update = self.export_parsed_csv(data)["Assessment"][0][field]
    self.assertEqual(after_update, "user@example.com")

  def test_import_last_deprecated_date(self):
    """Last Deprecated Date on assessment should be non editable."""
    with factories.single_commit():
      with freezegun.freeze_time("2017-01-01"):
        assessment = factories.AssessmentFactory(status="Deprecated")

    resp = self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("code", assessment.slug),
        ("Last Deprecated Date", "02/02/2017"),
    ]))

    result = models.Assessment.query.get(assessment.id)

    self.assertEqual(1, len(resp))
    self.assertEqual(1, resp[0]["updated"])
    self.assertEqual(result.end_date, datetime.date(2017, 1, 1))

  @ddt.data(*models.Assessment.VALID_STATES)
  def test_import_set_up_deprecated(self, start_state):
    """Update assessment from {0} to Deprecated."""
    with factories.single_commit():
      assessment = factories.AssessmentFactory(status=start_state)
    resp = self.import_data(
        OrderedDict([
            ("object_type", "Assessment"),
            ("code", assessment.slug),
            ("State", models.Assessment.DEPRECATED),
        ]))
    self.assertEqual(1, len(resp))

    self.assertEqual(1, resp[0]["updated"])
    self.assertEqual(
        models.Assessment.query.get(assessment.id).status,
        models.Assessment.DEPRECATED)

  def test_asmnt_cads_update_completed(self):
    """Test update of assessment without cads."""
    with factories.single_commit():
      audit = factories.AuditFactory()
      asmnt = factories.AssessmentFactory(audit=audit)
      factories.CustomAttributeDefinitionFactory(
          title="CAD",
          definition_type="assessment",
          definition_id=asmnt.id,
          attribute_type="Text",
          mandatory=True,
      )
    data = OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", asmnt.slug),
        ("Audit", audit.slug),
        ("Assignees", "user@example.com"),
        ("Creators", "user@example.com"),
        ("Title", "Test title"),
        ("State", "Completed"),
        ("CAD", "Some value"),
    ])
    for dry_run in [True, False]:
      response = self.import_data(data, dry_run=dry_run)
      self._check_csv_response(response, {})


@ddt.ddt
class TestAssessmentExport(TestCase):
  """Test Assessment object export."""

  def setUp(self):
    """ Set up for Assessment test cases """
    super(TestAssessmentExport, self).setUp()
    self.client.get("/login")
    self.headers = ObjectGenerator.get_header()

  def test_simple_export(self):
    """ Test full assessment export with no warnings

    CSV sheet:
      https://docs.google.com/spreadsheets/d/1Jg8jum2eQfvR3kZNVYbVKizWIGZXvfqv3yQpo2rIiD8/edit#gid=704933240&vpid=A7
    """

    self.import_file("assessment_full_no_warnings.csv")
    data = [{
        "object_name": "Assessment",
        "filters": {
            "expression": {}
        },
        "fields": "all",
    }]
    response = self.export_csv(data)
    self.assertIn(u"\u5555", response.data.decode("utf8"))

  def assertColumnExportedValue(self, value, instance, column):
    "Assertion checks is value equal to exported instance column value."
    data = [{
        "object_name": instance.__class__.__name__,
        "fields": "all",
        "filters": {
            "expression": {
                "text": str(instance.id),
                "op": {
                    "name": "text_search",
                }
            },
        },
    }]
    instance_dict = self.export_parsed_csv(data)[instance.type][0]
    self.assertEqual(value, instance_dict[column])

  def test_export_assesments_without_map_control(self):
    """Test export assesment without related control instance"""
    audit = factories.AuditFactory()
    assessment = factories.AssessmentFactory(audit=audit)
    factories.RelationshipFactory(source=audit, destination=assessment)
    control = factories.ControlFactory()
    revision = models.Revision.query.filter(
        models.Revision.resource_id == control.id,
        models.Revision.resource_type == control.__class__.__name__
    ).order_by(
        models.Revision.id.desc()
    ).first()
    factories.SnapshotFactory(
        parent=audit,
        child_id=control.id,
        child_type=control.__class__.__name__,
        revision_id=revision.id
    )
    db.session.commit()
    self.assertColumnExportedValue("", assessment,
                                   "map:control versions")

  @ddt.data(True, False)
  def test_export_assesments_map_control(self, with_map):
    """Test export assesment with and without related control instance"""
    with factories.single_commit():
      audit = factories.AuditFactory()
      assessment = factories.AssessmentFactory(audit=audit)
      factories.RelationshipFactory(source=audit, destination=assessment)
      control = factories.ControlFactory()
    revision = models.Revision.query.filter(
        models.Revision.resource_id == control.id,
        models.Revision.resource_type == control.__class__.__name__
    ).order_by(
        models.Revision.id.desc()
    ).first()
    with factories.single_commit():
      snapshot = factories.SnapshotFactory(
          parent=audit,
          child_id=control.id,
          child_type=control.__class__.__name__,
          revision_id=revision.id
      )
      if with_map:
        factories.RelationshipFactory(source=snapshot, destination=assessment)
    if with_map:
      val = control.slug
    else:
      val = ""
    self.assertColumnExportedValue(val, assessment,
                                   "map:control versions")

  def test_export_assesments_with_map_control_mirror_relation(self):
    """Test export assesment with related control instance

    relation assessment -> snapshot
    """
    with factories.single_commit():
      audit = factories.AuditFactory()
      assessment = factories.AssessmentFactory(audit=audit)
      factories.RelationshipFactory(source=audit, destination=assessment)
      control = factories.ControlFactory()
    revision = models.Revision.query.filter(
        models.Revision.resource_id == control.id,
        models.Revision.resource_type == control.__class__.__name__
    ).order_by(
        models.Revision.id.desc()
    ).first()
    snapshot = factories.SnapshotFactory(
        parent=audit,
        child_id=control.id,
        child_type=control.__class__.__name__,
        revision_id=revision.id
    )
    db.session.commit()
    factories.RelationshipFactory(destination=snapshot, source=assessment)
    self.assertColumnExportedValue(control.slug, assessment,
                                   "map:control versions")

  def test_export_assessments_with_filters_and_conflicting_ca_names(self):
    """Test exporting assessments with conflicting custom attribute names."""
    self.import_file(u"assessment_template_no_warnings.csv")
    self.import_file(u"assessment_with_templates.csv")

    # also create an object level custom attribute with a name that clashes
    # with a name of a "regular" attribute
    assessment = models.Assessment.query.filter(
        models.Assessment.slug == u"A 2").first()
    cad = models.CustomAttributeDefinition(
        attribute_type=u"Text",
        title=u"ca title",
        definition_type=u"assessment",
        definition_id=assessment.id
    )
    db.session.add(cad)
    db.session.commit()

    data = [{
        "object_name": "Assessment",
        "fields": ["slug", "title", "description", "status"],
        "filters": {
            "expression": {
                "left": {
                    "left": "code",
                    "op": {"name": "~"},
                    "right": "A 2"
                },
                "op": {"name": "AND"},
                "right": {
                    "left": "title",
                    "op": {"name": "~"},
                    "right": "no template Assessment"
                }
            },
            "keys": ["code", "title", "status"],
            "order_by": {
                "keys": [],
                "order": "",
                "compare": None
            }
        }
    }]

    response = self.export_csv(data)
    self.assertIn(u"No template Assessment 2", response.data)

  @ddt.data(
      ("Last Updated By", "new_user@email.com"),
      ("modified_by", "new_user1@email.com"),
  )
  @ddt.unpack
  def test_export_by_modified_by(self, field, email):
    "Test for creation assessment with mapped creator"
    slug = "TestAssessment"
    with factories.single_commit():
      factories.AssessmentFactory(
          slug=slug,
          modified_by=factories.PersonFactory(email=email),
      )
    data = [{
        "object_name": "Assessment",
        "fields": "all",
        "filters": {
            "expression": {
                "left": field,
                "op": {"name": "="},
                "right": email
            },
        }
    }]

    resp = self.export_parsed_csv(data)["Assessment"]
    self.assertEqual(1, len(resp))
    self.assertEqual(slug, resp[0]["Code*"])

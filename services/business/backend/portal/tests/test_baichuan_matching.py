"""Actual ORM acceptance of sourced rules, identities, dates and snapshots."""
from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import (BaichuanCertificate, BaichuanConversation,
    BaichuanEvidence, BaichuanFactRevision, BaichuanQualificationRule)
from portal.baichuan_conditions import compile_conditions
from portal.baichuan_jobs import claim_job, enqueue_job
from portal.baichuan_matching import company_facts, load_rules, match_companies, save_match_snapshot
from portal.baichuan_models import Company
from portal.baichuan_rules import install_compatibility_rules
from portal.baichuan_service import BaichuanError
from .base import PortalTestCase


def qualification(category="electronic", grade="2", **values):
    return dict(field="qualification", category=category, op="grade_exact", value=grade, holder="bidder", **values)


def conditions(node=None, **values):
    return dict(schema_version=1, revision=1, must=node or qualification(), **values)


class DeterministicMatchingTests(PortalTestCase):
    def setUp(self):
        for target in ("socket.create_connection", "socket.getaddrinfo", "portal.model_gateway.generate_for_use"):
            guard = patch(target, side_effect=AssertionError("matching acceptance forbids network and model calls"))
            mocked = guard.start()
            self.addCleanup(guard.stop)
            self.addCleanup(mocked.assert_not_called)
        self.owner = self.create_user("matching-owner", "product")
        self.today = timezone.localdate()
        config = override_settings(BAICHUAN_ASSISTANT_SCOPE="matching-isolated",
            PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.owner.pk], PORTAL_BAICHUAN_WRITE_USER_IDS=[self.owner.pk],
            PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        config.enable()
        self.addCleanup(config.disable)
        self.company = Company.objects.create(name="FICTIONAL MATCHING COMPANY", province="广东省", city="广州市",
            website="https://example.com/", website_kind="corporate", credit_code="916100000000000001",
            created_by=self.owner, updated_by=self.owner)

    def evidence(self, **values):
        args = dict(scope="matching-isolated", source_type="fixture", url="https://example.com/certificate",
            retrieved_at=timezone.now(), verified_on=self.today, content_hash="a" * 64,
            excerpt="Explicit synthetic evidence, not an actual company or certificate.", locator={"fixture": "page-1"},
            access_status="verified", subject=dict(company_id=str(self.company.pk), identity_verified=True,
                holder_type="bidder", authority="issuer", scope_verified=True, revocation_checked=True,
                revocation_checked_on=self.today.isoformat()))
        args.update(values)
        return BaichuanEvidence.objects.create(**args)

    def rule(self, category="electronic", **values):
        args = dict(category=category, version=1, legal_grades=["1", "2"], evidence=self.evidence())
        args.update(values)
        return BaichuanQualificationRule.objects.create(**args)

    def certificate(self, **values):
        args = dict(company=self.company, holder_company_id=self.company.pk, holder_type="bidder",
            holder_name=self.company.name, category="electronic", grade="2", verification_status="verified",
            assertion_status="PRESENT", valid_from=self.today-timedelta(days=1), valid_until=self.today+timedelta(days=30),
            revocation_status="clear", evidence=self.evidence())
        args.update(values)
        return BaichuanCertificate.objects.create(**args)

    def revision(self, evidence=None, **values):
        args = dict(company=self.company, field="province", actor=self.owner, baseline_version=1,
            new_value=self.company.province, verification_status="verified", review_status="applied",
            evidence=evidence or self.evidence())
        args.update(values)
        return BaichuanFactRevision.objects.create(**args)

    def match(self, payload=None):
        compiled, rules, rows, counts = match_companies(self.owner, payload or conditions())
        return rows[0], counts

    def test_official_host_identity_uses_current_company_and_rechecks_changed_host(self):
        subject = dict(company_id=str(self.company.pk), identity_verified=True,
            field_assertions={"province":[self.company.province]},
            identity_method="official_host_name_credit_code", identity_basis=dict(host="example.com",
                matched_name=self.company.name, matched_credit_code=self.company.credit_code))
        self.revision(self.evidence(subject=subject))
        payload = conditions(dict(field="company.province", op="eq", value="广东省"))
        self.assertEqual(self.match(payload)[0]["status"], "confirmed")
        self.company.website = "https://example.org/"
        self.company.save()
        self.assertEqual(self.match(payload)[0]["status"], "candidate")

    def test_publication_identity_cannot_verify_unquoted_field_value(self):
        subject=dict(company_id=str(self.company.pk), identity_verified=True,
            identity_method="full_legal_name_on_public_page", field_assertions={"province":["江苏省"]})
        self.revision(self.evidence(subject=subject))
        self.assertEqual(self.match(conditions(dict(field="company.province",op="eq",value="广东省")))[0]["status"],"candidate")

    def test_direct_fact_conversion_orders_latest_and_ignores_private_proposals(self):
        self.revision(review_status="proposed", verification_status="conflict")
        applied = self.revision()
        self.assertEqual(company_facts(self.company)["field_verification"]["province"]["status"], "verified")
        self.revision(review_status="manual", verification_status="unverified", evidence=None)
        self.assertNotIn("province", company_facts(self.company)["field_verification"])
        self.assertEqual(applied.review_status, "applied")

    def test_verified_province_hard_failure_is_excluded_despite_satisfied_preference(self):
        self.rule(); self.certificate(); self.revision()
        row, counts = self.match(conditions(dict(field="company.province", op="eq", value="江苏省"), should=[qualification()]))
        self.assertEqual((row["status"], row["preferences"], counts["excluded"]), ("excluded", ["satisfied"], 1))

    def test_parent_manufacturer_person_product_and_scope_cannot_confirm_bidder(self):
        self.rule()
        for changes in ({"holder_company_id": "00000000-0000-0000-0000-000000000001"},
                        {"holder_type": "manufacturer"}, {"holder_type": "person"}, {"holder_type": "product"},
                        {"holder_type": "consortium_member"}, {"holder_name": "FICTIONAL PARENT COMPANY"}):
            with self.subTest(changes=changes):
                cert = self.certificate(**changes)
                self.assertEqual(self.match()[0]["status"], "candidate")
                cert.delete()
        cert = self.certificate(scope_text="unrelated service")
        self.assertEqual(self.match(conditions(qualification(scope="required service")))[0]["status"], "candidate")

    def test_query_and_tender_dates_require_actual_revocation_check_at_that_date(self):
        self.rule()
        evidence = self.evidence(subject=dict(company_id=str(self.company.pk), identity_verified=True,
            holder_type="bidder", authority="issuer", scope_verified=True, revocation_checked=True,
            revocation_checked_on=self.today.isoformat(), revocation_as_of=(self.today+timedelta(days=10)).isoformat()))
        self.certificate(evidence=evidence)
        future = conditions(as_of=dict(date=(self.today+timedelta(days=10)).isoformat(), basis="tender_date"))
        self.assertEqual(self.match(future)[0]["status"], "candidate")

    def test_inclusive_date_boundaries_missing_dates_and_revocation_keep_citations(self):
        self.rule()
        for changes, expected in ((dict(valid_from=self.today, valid_until=self.today), "confirmed"),
            (dict(valid_until=self.today-timedelta(days=1)), "candidate"),
            (dict(valid_from=self.today+timedelta(days=1)), "candidate"),
            (dict(valid_from=None), "candidate"), (dict(valid_until=None), "candidate"),
            (dict(revocation_status="revoked"), "candidate"), (dict(revocation_status="suspended"), "candidate"),
            (dict(revocation_status="unknown"), "candidate")):
            with self.subTest(changes=changes):
                cert = self.certificate(**changes);row, _ = self.match()
                self.assertEqual(row["status"], expected)
                self.assertIn(str(cert.evidence_id), row["conditions"][0]["evidence_ids"])
                cert.delete()

    def test_future_evidence_and_inconsistent_check_date_never_verify(self):
        self.rule()
        for evidence in (self.evidence(verified_on=self.today+timedelta(days=1)),
                         self.evidence(retrieved_at=timezone.now()+timedelta(days=1)),
                         self.evidence(subject=dict(company_id=str(self.company.pk), identity_verified=True,
                            holder_type="bidder", authority="issuer", scope_verified=True, revocation_checked=True,
                            revocation_checked_on=(self.today-timedelta(days=1)).isoformat(), revocation_as_of=self.today.isoformat()))):
            with self.subTest(evidence=evidence.pk):
                cert=self.certificate(evidence=evidence)
                self.assertEqual(self.match()[0]["status"], "candidate")
                cert.delete()

    def test_exact_or_and_not_unknown_are_evaluated_without_lossy_prefilter(self):
        self.rule();self.rule("itss", legal_grades=["1","2","3","4"])
        self.certificate(grade="1");self.certificate(category="itss", grade="2")
        self.assertEqual(self.match()[0]["status"], "candidate")
        either = {"any":[qualification(grade="1"),qualification()]}
        row,_=self.match(conditions({"all":[either,qualification("itss")]}))
        self.assertEqual(row["status"],"confirmed")
        self.assertEqual([x["condition_id"] for x in row["conditions"]],["must.0.0","must.0.1","must.1"])
        self.assertEqual(self.match(conditions({"not":qualification("unsupported")}))[0]["status"],"candidate")

    def test_source_version_direction_and_disabled_rule_are_enforced(self):
        self.rule("cs",legal_grades=["1","2","3","4","5"],grade_relations={"at_least":{"2":["2","3","4","5"]}})
        self.rule("itss",legal_grades=["1","2","3","4"],grade_relations={"at_least":{"2":["1","2"]}})
        self.certificate(category="cs",grade="3");self.certificate(category="itss",grade="1")
        for category in ("cs","itss"):
            node=qualification(category);node["op"]="grade_at_least"
            self.assertEqual(self.match(conditions(node))[0]["status"],"confirmed")
            node["rule_version"]="different-version"
            self.assertEqual(self.match(conditions(node))[0]["status"],"candidate")
        self.rule("cs",version=2,enabled=False)
        self.assertFalse(load_rules(self.today)["cs"]["enabled"])

    def test_incomplete_or_snippet_rule_basis_cannot_enable_relationship(self):
        self.certificate()
        for values in ({"content_hash":""},{"source_type":"search_snippet"},{"verified_on":self.today+timedelta(days=1)},
                       {"retrieved_at":timezone.now()+timedelta(days=1)}):
            with self.subTest(values=values):
                self.rule(version=BaichuanQualificationRule.objects.count()+1,evidence=self.evidence(**values))
                self.assertEqual(self.match()[0]["status"],"candidate")

    def test_malformed_relation_is_unknown_without_crashing_or_accepting_unknown_grade(self):
        self.certificate(grade="outside-dictionary")
        for relations in ([], {"at_least":[]}, {"at_least":{"2":["2","outside-dictionary"]}}):
            with self.subTest(relations=relations):
                self.rule(version=BaichuanQualificationRule.objects.count()+1,grade_relations=relations)
                node=qualification();node["op"]="grade_at_least"
                self.assertEqual(self.match(conditions(node))[0]["status"],"candidate")

    def test_rules_install_maintains_exact_seven_and_conservative_unsupported_order(self):
        self.assertEqual(len(install_compatibility_rules(self.owner)),7)
        self.assertEqual(install_compatibility_rules(self.owner),[])
        loaded=load_rules(self.today)
        self.assertEqual(len(loaded),7)
        self.assertEqual(loaded["cs"]["at_least"]["2"],["2","3","4","5"])
        self.assertEqual(loaded["itss"]["at_least"],{})
        self.certificate(category="itss")
        node=qualification("itss");node["op"]="grade_at_least"
        self.assertEqual(self.match(conditions(node))[0]["status"],"candidate")

    def test_rule_applicability_and_certificate_standard_do_not_silently_fallback(self):
        cert=self.certificate(standard="old-standard")
        self.rule(applicable_from=self.today+timedelta(days=1))
        self.assertEqual(self.match()[0]["status"],"candidate")
        self.rule(version=2,applicable_until=self.today-timedelta(days=1))
        self.assertEqual(self.match()[0]["status"],"candidate")
        self.rule(version=3,standard="current-standard")
        self.assertEqual(self.match()[0]["status"],"candidate")
        cert.standard="current-standard";cert.save()
        self.assertEqual(self.match()[0]["status"],"confirmed")
        _,rules,_,_=match_companies(self.owner,conditions())
        self.assertEqual(rules["electronic"]["version"],"electronic:3")

    def test_unknown_companies_remain_and_lexicographic_preferences_sort_stably(self):
        others=[Company.objects.create(name="AAA FICTIONAL",created_by=self.owner,updated_by=self.owner) for _ in range(2)]
        self.revision()
        payload=conditions(qualification("unsupported"),should=[dict(field="company.province",op="eq",value="广东省")])
        compiled,_,rows,counts=match_companies(self.owner,payload)
        self.assertEqual(counts,{"confirmed":0,"candidate":3,"excluded":0})
        self.assertEqual(rows[0]["company_id"],str(self.company.pk))
        self.assertEqual([r["company_id"] for r in rows[1:]],sorted(str(c.pk) for c in others))
        self.assertEqual(match_companies(self.owner,payload)[2],rows)
        self.assertEqual(compiled["as_of"],{"date":self.today.isoformat(),"basis":"query_date"})

    def test_stale_user_object_cannot_match_after_account_revocation(self):
        type(self.owner).objects.filter(pk=self.owner.pk).update(is_active=False)
        with self.assertRaises(BaichuanError):self.match()

    def test_snapshot_freezes_original_evidence_counts_and_replay(self):
        self.rule();cert=self.certificate()
        conversation=BaichuanConversation.objects.create(owner=self.owner,scope="matching-isolated",condition_revision=1)
        job,_=enqueue_job(self.owner,kind="query",payload={"condition_revision":1},idempotency_key="match-snapshot",conversation=conversation)
        job=claim_job("matching-worker",job_id=job.pk)
        original=save_match_snapshot(self.owner,job.pk,"matching-worker",job.fence,conditions())
        self.assertEqual(original.counts["confirmed"],1)
        self.assertEqual(save_match_snapshot(self.owner,job.pk,"matching-worker",job.fence,conditions()).pk,original.pk)
        cert.verification_status="unverified";cert.save()
        later=save_match_snapshot(self.owner,job.pk,"matching-worker",job.fence,conditions(),result_revision=2)
        self.assertEqual(later.counts["candidate"],1)
        original.refresh_from_db();self.assertEqual(original.counts["confirmed"],1)
        self.assertEqual(original.results[0]["conditions"][0]["evidence_ids"],[str(cert.evidence_id)])

    def test_certificate_metadata_is_bound_to_company_scope_category_and_cited_condition(self):
        self.rule()
        source = self.evidence()
        own = self.certificate(evidence=source, certificate_no='001239', issuer='FICTIONAL ISSUER')
        # Sharing an evidence ID does not license unrelated certificate metadata.
        self.certificate(evidence=source, category='itss', certificate_no='UNRELATED-CATEGORY')
        self.certificate(evidence=self.evidence(scope='other-scope'), certificate_no='OTHER-SCOPE')
        self.certificate(evidence=self.evidence(subject={'company_id': 'other-company'}), certificate_no='OTHER-SUBJECT')
        other = Company.objects.create(name='OTHER FICTIONAL COMPANY', created_by=self.owner, updated_by=self.owner)
        self.certificate(company=other, evidence=source, certificate_no='OTHER-COMPANY')
        row, counts = self.match()
        metadata = row['certificate_records']
        self.assertEqual([record['certificate_no'] for record in metadata], ['001239'])
        self.assertEqual(metadata[0]['certificate_id'], str(own.pk))
        self.assertEqual(metadata[0]['company_id'], str(self.company.pk))
        self.assertEqual(metadata[0]['evidence_id'], str(source.pk))
        self.assertEqual(metadata[0]['condition_ids'], ['must'])
        self.assertEqual(metadata[0]['holder_type'], 'bidder')
        self.assertEqual(metadata[0]['issuer'], 'FICTIONAL ISSUER')

    def test_unverified_manufacturer_metadata_preserves_actual_holder_and_unknown_verdict(self):
        self.rule()
        cert = self.certificate(holder_type='manufacturer', holder_name='FICTIONAL MANUFACTURER',
            verification_status='unverified', certificate_no='000099')
        row, counts = self.match(conditions({**qualification(), 'holder': 'manufacturer'}))
        self.assertEqual((row['status'], counts['confirmed']), ('candidate', 0))
        record = row['certificate_records'][0]
        self.assertEqual((record['holder_type'], record['holder_name'], record['verification_status']),
            ('manufacturer', 'FICTIONAL MANUFACTURER', 'unverified'))
        self.assertEqual(record['certificate_id'], str(cert.pk))

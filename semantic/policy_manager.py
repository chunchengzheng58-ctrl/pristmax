"""
Policy Manager

Manages policy lifecycle:
- Policy creation, versioning, and storage
- Policy change history
- Policy validation and templates
- Policy deployment
"""

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from threading import Lock


class PolicyStatus(Enum):
    """Policy lifecycle status"""
    DRAFT = "draft"               # Being created, not active
    ACTIVE = "active"             # Currently in use
    SUSPENDED = "suspended"       # Temporarily disabled
    ARCHIVED = "archived"         # No longer used, kept for history


@dataclass
class PolicyVersion:
    """A specific version of a policy"""
    version_id: str
    policy_id: str
    version_number: int
    created_at: str
    created_by: str
    config: Dict                 # Full policy configuration
    change_summary: str          # What changed in this version
    status: PolicyStatus

    def to_dict(self) -> Dict:
        return {
            'version_id': self.version_id,
            'policy_id': self.policy_id,
            'version_number': self.version_number,
            'created_at': self.created_at,
            'created_by': self.created_by,
            'config': self.config,
            'change_summary': self.change_summary,
            'status': self.status.value,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'PolicyVersion':
        return cls(
            version_id=data['version_id'],
            policy_id=data['policy_id'],
            version_number=data['version_number'],
            created_at=data['created_at'],
            created_by=data['created_by'],
            config=data['config'],
            change_summary=data['change_summary'],
            status=PolicyStatus(data['status']),
        )


@dataclass
class PolicyChangeRecord:
    """Record of a policy change"""
    change_id: str
    policy_id: str
    version_from: int
    version_to: int
    changed_at: str
    changed_by: str
    change_type: str             # create, update, suspend, activate, archive
    reason: str
    approver: str = ""           # Who approved the change
    approved_at: str = ""


class PolicyManager:
    """
    Manages policy lifecycle and versioning.

    Features:
    - Create and update policies with version control
    - Policy templates for common scenarios
    - Policy validation before activation
    - Change history and audit trail
    - Rollback capability
    """

    def __init__(self, storage_path: str, config: Dict = None):
        """
        Args:
            storage_path: Directory for policy storage
            config: Configuration options
        """
        self.storage_path = Path(storage_path)
        self.config = config or {}

        # Ensure directory exists
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Index file for quick lookup
        self.index_file = self.storage_path / "policy_index.json"
        self._lock = Lock()

        # Load or create index
        self._index = self._load_index()

    def _load_index(self) -> Dict:
        """Load policy index"""
        if self.index_file.exists():
            with open(self.index_file, 'r') as f:
                return json.load(f)
        return {'policies': {}, 'versions': {}}

    def _save_index(self):
        """Save policy index"""
        with self._lock:
            with open(self.index_file, 'w') as f:
                json.dump(self._index, f, indent=2)

    def create_policy(
        self,
        name: str,
        policy_type: str,
        config: Dict,
        created_by: str = "system",
        reason: str = "Initial creation"
    ) -> PolicyVersion:
        """
        Create a new policy.

        Args:
            name: Policy name
            policy_type: Type (surveillance, log, etc.)
            config: Policy configuration
            created_by: Who created the policy
            reason: Reason for creation

        Returns:
            PolicyVersion object
        """
        policy_id = uuid.uuid4().hex[:16]
        version_id = uuid.uuid4().hex

        version = PolicyVersion(
            version_id=version_id,
            policy_id=policy_id,
            version_number=1,
            created_at=datetime.utcnow().isoformat() + 'Z',
            created_by=created_by,
            config={
                'name': name,
                'type': policy_type,
                **config
            },
            change_summary=reason,
            status=PolicyStatus.DRAFT
        )

        # Store version
        self._store_version(version)

        # Update index
        self._index['policies'][policy_id] = {
            'name': name,
            'type': policy_type,
            'created_at': version.created_at,
            'current_version': 1,
            'status': PolicyStatus.DRAFT.value
        }
        self._index['versions'][version_id] = {
            'policy_id': policy_id,
            'version_number': 1
        }
        self._save_index()

        return version

    def update_policy(
        self,
        policy_id: str,
        config: Dict,
        updated_by: str,
        reason: str,
        approver: str = ""
    ) -> PolicyVersion:
        """
        Update an existing policy (creates new version).

        Args:
            policy_id: Policy ID to update
            config: New configuration
            updated_by: Who made the update
            reason: Reason for update
            approver: Who approved (if required)

        Returns:
            New PolicyVersion object
        """
        current = self.get_current_version(policy_id)
        if not current:
            raise ValueError(f"Policy {policy_id} not found")

        new_version_number = current.version_number + 1
        version_id = uuid.uuid4().hex

        version = PolicyVersion(
            version_id=version_id,
            policy_id=policy_id,
            version_number=new_version_number,
            created_at=datetime.utcnow().isoformat() + 'Z',
            created_by=updated_by,
            config={**current.config, **{k: v for k, v in config.items() if not k.startswith('_')}},
            change_summary=reason,
            status=PolicyStatus(config.get('_status', current.status.value))
        )

        # Store version
        self._store_version(version)

        # Update index
        self._index['policies'][policy_id]['current_version'] = new_version_number
        self._index['versions'][version_id] = {
            'policy_id': policy_id,
            'version_number': new_version_number
        }
        self._save_index()

        # Record change
        self._record_change(PolicyChangeRecord(
            change_id=uuid.uuid4().hex,
            policy_id=policy_id,
            version_from=current.version_number,
            version_to=new_version_number,
            changed_at=version.created_at,
            changed_by=updated_by,
            change_type='update',
            reason=reason,
            approver=approver,
            approved_at=datetime.utcnow().isoformat() + 'Z' if approver else ''
        ))

        return version

    def activate_policy(self, policy_id: str, activated_by: str) -> PolicyVersion:
        """Activate a draft policy"""
        current = self.get_current_version(policy_id)
        if not current:
            raise ValueError(f"Policy {policy_id} not found")

        if current.status != PolicyStatus.DRAFT:
            raise ValueError(f"Policy {policy_id} is not in DRAFT status")

        # Create new version with ACTIVE status
        new_config = {**current.config, '_status': PolicyStatus.ACTIVE.value}
        return self.update_policy(
            policy_id,
            new_config,
            activated_by,
            "Policy activated",
            approver=activated_by
        )

    def suspend_policy(self, policy_id: str, suspended_by: str, reason: str) -> PolicyVersion:
        """Suspend an active policy"""
        current = self.get_current_version(policy_id)
        if not current:
            raise ValueError(f"Policy {policy_id} not found")

        if current.status != PolicyStatus.ACTIVE:
            raise ValueError(f"Policy {policy_id} is not ACTIVE")

        return self.update_policy(
            policy_id,
            {**current.config},
            suspended_by,
            f"Suspended: {reason}"
        )

    def archive_policy(self, policy_id: str, archived_by: str, reason: str) -> PolicyVersion:
        """Archive a policy"""
        current = self.get_current_version(policy_id)
        if not current:
            raise ValueError(f"Policy {policy_id} not found")

        version = self.update_policy(
            policy_id,
            {**current.config},
            archived_by,
            f"Archived: {reason}"
        )

        # Update status in index
        self._index['policies'][policy_id]['status'] = PolicyStatus.ARCHIVED.value
        self._save_index()

        return version

    def rollback_policy(self, policy_id: str, target_version: int, rolled_back_by: str, reason: str) -> PolicyVersion:
        """
        Rollback to a previous version.

        Args:
            policy_id: Policy ID
            target_version: Version number to rollback to
            rolled_back_by: Who initiated rollback
            reason: Reason for rollback

        Returns:
            New PolicyVersion (copied from target)
        """
        target = self.get_version(policy_id, target_version)
        if not target:
            raise ValueError(f"Version {target_version} of policy {policy_id} not found")

        # Create new version with target's config
        new_version = self.update_policy(
            policy_id,
            {**target.config},
            rolled_back_by,
            f"Rollback to v{target_version}: {reason}"
        )

        return new_version

    def get_current_version(self, policy_id: str) -> Optional[PolicyVersion]:
        """Get current version of a policy"""
        if policy_id not in self._index['policies']:
            return None

        current_num = self._index['policies'][policy_id]['current_version']
        return self.get_version(policy_id, current_num)

    def get_version(self, policy_id: str, version_number: int) -> Optional[PolicyVersion]:
        """Get specific version of a policy"""
        # Find version_id
        for vid, info in self._index['versions'].items():
            if info['policy_id'] == policy_id and info['version_number'] == version_number:
                return self._load_version(vid)
        return None

    def get_policy_history(self, policy_id: str) -> List[PolicyVersion]:
        """Get full version history of a policy"""
        versions = []

        if policy_id not in self._index['policies']:
            return versions

        current_num = self._index['policies'][policy_id]['current_version']

        for vn in range(1, current_num + 1):
            version = self.get_version(policy_id, vn)
            if version:
                versions.append(version)

        return versions

    def list_policies(self, status: Optional[PolicyStatus] = None) -> List[Dict]:
        """List all policies, optionally filtered by status"""
        policies = []

        for pid, info in self._index['policies'].items():
            if status and info['status'] != status.value:
                continue
            policies.append({
                'policy_id': pid,
                'name': info['name'],
                'type': info['type'],
                'created_at': info['created_at'],
                'current_version': info['current_version'],
                'status': info['status']
            })

        return policies

    def get_change_history(self, policy_id: str) -> List[PolicyChangeRecord]:
        """Get change history for a policy"""
        history_file = self.storage_path / f"{policy_id}_changes.json"
        if not history_file.exists():
            return []

        with open(history_file, 'r') as f:
            records = json.load(f)
            return [PolicyChangeRecord(**r) for r in records]

    def _store_version(self, version: PolicyVersion):
        """Store version to file"""
        version_file = self.storage_path / f"{version.version_id}.json"
        with open(version_file, 'w') as f:
            json.dump(version.to_dict(), f, indent=2)

    def _load_version(self, version_id: str) -> Optional[PolicyVersion]:
        """Load version from file"""
        version_file = self.storage_path / f"{version_id}.json"
        if not version_file.exists():
            return None

        with open(version_file, 'r') as f:
            data = json.load(f)
            return PolicyVersion.from_dict(data)

    def _record_change(self, record: PolicyChangeRecord):
        """Record a policy change"""
        history_file = self.storage_path / f"{record.policy_id}_changes.json"

        records = []
        if history_file.exists():
            with open(history_file, 'r') as f:
                records = json.load(f)

        records.append({
            'change_id': record.change_id,
            'policy_id': record.policy_id,
            'version_from': record.version_from,
            'version_to': record.version_to,
            'changed_at': record.changed_at,
            'changed_by': record.changed_by,
            'change_type': record.change_type,
            'reason': record.reason,
            'approver': record.approver,
            'approved_at': record.approved_at,
        })

        with open(history_file, 'w') as f:
            json.dump(records, f, indent=2)

    def validate_policy(self, config: Dict, policy_type: str) -> Dict[str, Any]:
        """
        Validate a policy configuration.

        Returns:
            Dict with 'valid' (bool) and 'errors' (list)
        """
        errors = []

        # Basic required fields
        if not config.get('name'):
            errors.append("Policy name is required")

        # Type-specific validation
        if policy_type == 'surveillance':
            if 'preserve_with_faces' in config and not isinstance(config['preserve_with_faces'], bool):
                errors.append("preserve_with_faces must be boolean")
            if 'retain_days_critical' in config:
                if not isinstance(config['retain_days_critical'], int) or config['retain_days_critical'] < 0:
                    errors.append("retain_days_critical must be a positive integer")

        elif policy_type == 'log':
            if 'level_rules' in config:
                if not isinstance(config['level_rules'], list):
                    errors.append("level_rules must be a list")

        return {
            'valid': len(errors) == 0,
            'errors': errors
        }

    def create_from_template(self, template_name: str, name: str, created_by: str) -> PolicyVersion:
        """
        Create a policy from a built-in template.

        Args:
            template_name: Name of template (e.g., 'surveillance_indoor', 'log_default')
            name: Name for the new policy
            created_by: Who is creating it

        Returns:
            New PolicyVersion
        """
        templates = self._get_templates()
        if template_name not in templates:
            raise ValueError(f"Template '{template_name}' not found")

        return self.create_policy(
            name=name,
            policy_type=templates[template_name]['type'],
            config=templates[template_name]['config'],
            created_by=created_by,
            reason=f"Created from template: {template_name}"
        )

    def _get_templates(self) -> Dict:
        """Get built-in policy templates"""
        return {
            'surveillance_indoor': {
                'type': 'surveillance',
                'config': {
                    'preserve_with_faces': True,
                    'preserve_with_people': True,
                    'preserve_with_vehicles': False,
                    'low_value_downsample_ratio': 0.1,
                    'retain_days_critical': 365,
                    'retain_days_high': 90,
                    'retain_days_medium': 30,
                    'retain_days_low': 7,
                }
            },
            'surveillance_parking': {
                'type': 'surveillance',
                'config': {
                    'preserve_with_faces': True,
                    'preserve_with_people': True,
                    'preserve_with_vehicles': True,
                    'low_value_downsample_ratio': 0.05,
                    'retain_days_critical': 365,
                    'retain_days_high': 90,
                    'retain_days_medium': 30,
                    'retain_days_low': 7,
                }
            },
            'log_application': {
                'type': 'log',
                'config': {
                    'preserve_order_logs': True,
                    'preserve_transaction_logs': True,
                    'default_sampling_rate': 0.1,
                    'retain_days_critical': 365,
                    'retain_days_high': 90,
                    'retain_days_medium': 30,
                    'retain_days_low': 7,
                }
            },
            'log_access': {
                'type': 'log',
                'config': {
                    'preserve_order_logs': False,
                    'preserve_transaction_logs': False,
                    'default_sampling_rate': 0.05,
                    'retain_days_critical': 180,
                    'retain_days_high': 90,
                    'retain_days_medium': 30,
                    'retain_days_low': 7,
                }
            },
        }

    def export_policy(self, policy_id: str, output_path: str) -> str:
        """Export policy to JSON file"""
        version = self.get_current_version(policy_id)
        if not version:
            raise ValueError(f"Policy {policy_id} not found")

        with open(output_path, 'w') as f:
            json.dump({
                'policy_id': policy_id,
                'name': version.config.get('name'),
                'type': version.config.get('type'),
                'current_version': version.version_number,
                'status': version.status.value,
                'created_at': version.created_at,
                'created_by': version.created_by,
                'config': version.config,
                'history': [v.to_dict() for v in self.get_policy_history(policy_id)]
            }, f, indent=2)

        return output_path

    def import_policy(self, input_path: str, imported_by: str) -> PolicyVersion:
        """Import policy from JSON file"""
        with open(input_path, 'r') as f:
            data = json.load(f)

        return self.create_policy(
            name=data['name'],
            policy_type=data.get('type', 'custom'),
            config=data['config'],
            created_by=imported_by,
            reason="Imported from file"
        )


# Demo usage
if __name__ == '__main__':
    import tempfile

    print("Policy Manager Demo")
    print("="*50)

    # Create temp storage
    temp_dir = tempfile.mkdtemp()
    manager = PolicyManager(temp_dir)

    print(f"\nStorage path: {temp_dir}")

    # Create a policy from template
    print("\nCreating policy from template...")
    policy = manager.create_from_template(
        'surveillance_indoor',
        'Office Building Floor 3',
        'admin'
    )
    print(f"  Created: {policy.policy_id}")
    print(f"  Version: {policy.version_number}")
    print(f"  Status: {policy.status.value}")

    # Activate it
    print("\nActivating policy...")
    active = manager.activate_policy(policy.policy_id, 'admin')
    print(f"  Status: {active.status.value}")

    # Update policy
    print("\nUpdating policy...")
    updated = manager.update_policy(
        policy.policy_id,
        {'low_value_downsample_ratio': 0.05},
        'security_admin',
        'Increased reduction for better storage savings'
    )
    print(f"  New version: {updated.version_number}")

    # List policies
    print("\nListing policies:")
    for p in manager.list_policies():
        print(f"  {p['policy_id']}: {p['name']} ({p['status']}) v{p['current_version']}")

    # Get history
    print("\nPolicy history:")
    for v in manager.get_policy_history(policy.policy_id):
        print(f"  v{v.version_number}: {v.change_summary} ({v.created_at})")

    # Rollback demo
    print("\nRolling back to v1...")
    rolled = manager.rollback_policy(policy.policy_id, 1, 'admin', 'Configuration error')
    print(f"  New version: {rolled.version_number} (based on v1 config)")

    # Cleanup
    import shutil
    shutil.rmtree(temp_dir)
    print("\n[Cleaned up temp storage]")

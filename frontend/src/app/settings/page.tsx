'use client';

import { useState, useEffect } from 'react';
import Card from '../../components/Card';
import Loading from '../../components/Loading';
import PageHeader from '../../components/PageHeader';
import { Alert } from '../../components/Alert';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface CompanySettings {
  company_name: string;
  business_number: string;
  address: string;
  business_type: string;
  business_item: string;
  bank_name: string;
  account_holder: string;
  account_number: string;
  representative: string;
  updated_at?: string;
}

const defaultSettings: CompanySettings = {
  company_name: '',
  business_number: '',
  address: '',
  business_type: '',
  business_item: '',
  bank_name: '',
  account_holder: '',
  account_number: '',
  representative: '',
};

export default function SettingsPage() {
  const [settings, setSettings] = useState<CompanySettings>(defaultSettings);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    const storedIsAdmin = localStorage.getItem('isAdmin') === 'true';
    setIsAdmin(storedIsAdmin);
    loadSettings();
  }, []);

  async function loadSettings() {
    try {
      setLoading(true);
      const res = await fetch(`${API_URL}/settings/company`);
      if (res.ok) {
        const data = await res.json();
        setSettings(data);
      }
    } catch (err) {
      setError('설정을 불러오는데 실패했습니다.');
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    if (!isAdmin) {
      setError('관리자만 설정을 수정할 수 있습니다.');
      return;
    }

    try {
      setSaving(true);
      setError(null);
      
      const res = await fetch(`${API_URL}/settings/company`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });

      if (!res.ok) {
        throw new Error('저장 실패');
      }

      const data = await res.json();
      setSettings(data);
      setSuccess('설정이 저장되었습니다.');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : '저장 실패');
    } finally {
      setSaving(false);
    }
  }

  function handleChange(field: keyof CompanySettings, value: string) {
    setSettings(prev => ({ ...prev, [field]: value }));
  }

  if (loading) {
    return <Loading />;
  }

  return (
    <div>
      <PageHeader title="회사 설정" subtitle="사업자 정보 및 계좌 정보를 관리합니다" />

      {error && <Alert type="error" message={error} />}
      {success && <Alert type="success" message={success} />}

      {!isAdmin && (
        <Alert type="warning" message="관리자만 설정을 수정할 수 있습니다. (읽기 전용)" />
      )}

      <Card title="사업자 정보">
        <div className="data-form-grid">
          <div className="form-group">
            <label className="ops-label">상호 (회사명)</label>
            <input
              type="text"
              value={settings.company_name}
              onChange={(e) => handleChange('company_name', e.target.value)}
              className="ui-control"
              disabled={!isAdmin}
            />
          </div>
          <div className="form-group">
            <label className="ops-label">사업자번호</label>
            <input
              type="text"
              value={settings.business_number}
              onChange={(e) => handleChange('business_number', e.target.value)}
              className="ui-control"
              placeholder="000-00-00000"
              disabled={!isAdmin}
            />
          </div>
        </div>

        <div className="form-group">
          <label className="ops-label">소재지 (주소)</label>
          <input
            type="text"
            value={settings.address}
            onChange={(e) => handleChange('address', e.target.value)}
            className="ui-control"
            disabled={!isAdmin}
          />
        </div>

        <div className="data-form-grid">
          <div className="form-group">
            <label className="ops-label">업태</label>
            <input
              type="text"
              value={settings.business_type}
              onChange={(e) => handleChange('business_type', e.target.value)}
              className="ui-control"
              disabled={!isAdmin}
            />
          </div>
          <div className="form-group">
            <label className="ops-label">종목</label>
            <input
              type="text"
              value={settings.business_item}
              onChange={(e) => handleChange('business_item', e.target.value)}
              className="ui-control"
              disabled={!isAdmin}
            />
          </div>
        </div>

        <div className="form-group">
          <label className="ops-label">대표자명</label>
          <input
            type="text"
            value={settings.representative}
            onChange={(e) => handleChange('representative', e.target.value)}
            className="ui-control"
            disabled={!isAdmin}
          />
        </div>
      </Card>

      <Card title="계좌 정보" className="tw-mt-3">
        <div className="data-form-grid">
          <div className="form-group">
            <label className="ops-label">은행명</label>
            <input
              type="text"
              value={settings.bank_name}
              onChange={(e) => handleChange('bank_name', e.target.value)}
              className="ui-control"
              disabled={!isAdmin}
            />
          </div>
          <div className="form-group">
            <label className="ops-label">예금주</label>
            <input
              type="text"
              value={settings.account_holder}
              onChange={(e) => handleChange('account_holder', e.target.value)}
              className="ui-control"
              disabled={!isAdmin}
            />
          </div>
          <div className="form-group">
            <label className="ops-label">계좌번호</label>
            <input
              type="text"
              value={settings.account_number}
              onChange={(e) => handleChange('account_number', e.target.value)}
              className="ui-control"
              disabled={!isAdmin}
            />
          </div>
        </div>
      </Card>

      {isAdmin && (
        <div className="tw-mt-4 tw-text-right">
          <button
            onClick={handleSave}
            disabled={saving}
            className="btn btn-success"
          >
            {saving ? '저장 중...' : '설정 저장'}
          </button>
        </div>
      )}

      {settings.updated_at && (
        <p className="caption tw-mt-3">마지막 수정: {settings.updated_at}</p>
      )}
    </div>
  );
}


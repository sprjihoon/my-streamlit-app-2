'use client';

import { useState, useEffect } from 'react';
import Card from '../../components/Card';
import Loading from '../../components/Loading';

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

interface ExtraFeeItem {
  항목: string;
  단가: number;
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
  const [extraFees, setExtraFees] = useState<ExtraFeeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingFees, setSavingFees] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [newItemName, setNewItemName] = useState('');
  const [newItemPrice, setNewItemPrice] = useState(0);

  useEffect(() => {
    const storedIsAdmin = localStorage.getItem('isAdmin') === 'true';
    setIsAdmin(storedIsAdmin);
    loadSettings();
    loadExtraFees();
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

  async function loadExtraFees() {
    try {
      const res = await fetch(`${API_URL}/settings/extra-fees`);
      if (res.ok) {
        const data = await res.json();
        setExtraFees(data);
      }
    } catch (err) {
      console.error('부가 서비스 단가 로딩 실패:', err);
    }
  }

  async function handleUpdateExtraFee(itemName: string, newPrice: number) {
    if (!isAdmin) {
      setError('관리자만 설정을 수정할 수 있습니다.');
      return;
    }

    try {
      setSavingFees(true);
      const res = await fetch(`${API_URL}/settings/extra-fees/${encodeURIComponent(itemName)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 단가: newPrice }),
      });

      if (!res.ok) throw new Error('저장 실패');

      await loadExtraFees();
      setSuccess(`'${itemName}' 단가가 저장되었습니다.`);
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : '저장 실패');
    } finally {
      setSavingFees(false);
    }
  }

  async function handleAddExtraFee() {
    if (!isAdmin) {
      setError('관리자만 설정을 수정할 수 있습니다.');
      return;
    }

    if (!newItemName.trim()) {
      setError('항목명을 입력해주세요.');
      return;
    }

    try {
      setSavingFees(true);
      const res = await fetch(`${API_URL}/settings/extra-fees`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 항목: newItemName.trim(), 단가: newItemPrice }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || '추가 실패');
      }

      await loadExtraFees();
      setNewItemName('');
      setNewItemPrice(0);
      setSuccess(`'${newItemName}' 항목이 추가되었습니다.`);
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : '추가 실패');
    } finally {
      setSavingFees(false);
    }
  }

  async function handleDeleteExtraFee(itemName: string) {
    if (!isAdmin) {
      setError('관리자만 설정을 수정할 수 있습니다.');
      return;
    }

    if (!confirm(`'${itemName}' 항목을 삭제하시겠습니까?`)) return;

    try {
      setSavingFees(true);
      const res = await fetch(`${API_URL}/settings/extra-fees/${encodeURIComponent(itemName)}`, {
        method: 'DELETE',
      });

      if (!res.ok) throw new Error('삭제 실패');

      await loadExtraFees();
      setSuccess(`'${itemName}' 항목이 삭제되었습니다.`);
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : '삭제 실패');
    } finally {
      setSavingFees(false);
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

  const inputStyle = {
    width: '100%',
    padding: '0.5rem',
    border: '1px solid #ddd',
    borderRadius: '4px',
    fontSize: '0.9rem',
  };

  const labelStyle = {
    display: 'block',
    marginBottom: '0.25rem',
    fontWeight: 'bold' as const,
    color: '#333',
  };

  const fieldGroupStyle = {
    marginBottom: '1rem',
  };

  if (loading) {
    return <Loading />;
  }

  return (
    <div style={{ padding: '1rem' }}>
      <h1 style={{ marginBottom: '1.5rem' }}>⚙️ 회사 설정</h1>

      {error && (
        <div style={{ 
          padding: '1rem', 
          backgroundColor: '#ffebee', 
          color: '#c62828', 
          borderRadius: '4px',
          marginBottom: '1rem'
        }}>
          {error}
        </div>
      )}

      {success && (
        <div style={{ 
          padding: '1rem', 
          backgroundColor: '#e8f5e9', 
          color: '#2e7d32', 
          borderRadius: '4px',
          marginBottom: '1rem'
        }}>
          {success}
        </div>
      )}

      {!isAdmin && (
        <div style={{ 
          padding: '1rem', 
          backgroundColor: '#fff3e0', 
          color: '#e65100', 
          borderRadius: '4px',
          marginBottom: '1rem'
        }}>
          ⚠️ 관리자만 설정을 수정할 수 있습니다. (읽기 전용)
        </div>
      )}

      <Card title="🏢 사업자 정보">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div style={fieldGroupStyle}>
            <label style={labelStyle}>상호 (회사명)</label>
            <input
              type="text"
              value={settings.company_name}
              onChange={(e) => handleChange('company_name', e.target.value)}
              style={inputStyle}
              disabled={!isAdmin}
            />
          </div>
          <div style={fieldGroupStyle}>
            <label style={labelStyle}>사업자번호</label>
            <input
              type="text"
              value={settings.business_number}
              onChange={(e) => handleChange('business_number', e.target.value)}
              style={inputStyle}
              placeholder="000-00-00000"
              disabled={!isAdmin}
            />
          </div>
        </div>

        <div style={fieldGroupStyle}>
          <label style={labelStyle}>소재지 (주소)</label>
          <input
            type="text"
            value={settings.address}
            onChange={(e) => handleChange('address', e.target.value)}
            style={inputStyle}
            disabled={!isAdmin}
          />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div style={fieldGroupStyle}>
            <label style={labelStyle}>업태</label>
            <input
              type="text"
              value={settings.business_type}
              onChange={(e) => handleChange('business_type', e.target.value)}
              style={inputStyle}
              disabled={!isAdmin}
            />
          </div>
          <div style={fieldGroupStyle}>
            <label style={labelStyle}>종목</label>
            <input
              type="text"
              value={settings.business_item}
              onChange={(e) => handleChange('business_item', e.target.value)}
              style={inputStyle}
              disabled={!isAdmin}
            />
          </div>
        </div>

        <div style={fieldGroupStyle}>
          <label style={labelStyle}>대표자명</label>
          <input
            type="text"
            value={settings.representative}
            onChange={(e) => handleChange('representative', e.target.value)}
            style={inputStyle}
            disabled={!isAdmin}
          />
        </div>
      </Card>

      <Card title="🏦 계좌 정보" style={{ marginTop: '1rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
          <div style={fieldGroupStyle}>
            <label style={labelStyle}>은행명</label>
            <input
              type="text"
              value={settings.bank_name}
              onChange={(e) => handleChange('bank_name', e.target.value)}
              style={inputStyle}
              disabled={!isAdmin}
            />
          </div>
          <div style={fieldGroupStyle}>
            <label style={labelStyle}>예금주</label>
            <input
              type="text"
              value={settings.account_holder}
              onChange={(e) => handleChange('account_holder', e.target.value)}
              style={inputStyle}
              disabled={!isAdmin}
            />
          </div>
          <div style={fieldGroupStyle}>
            <label style={labelStyle}>계좌번호</label>
            <input
              type="text"
              value={settings.account_number}
              onChange={(e) => handleChange('account_number', e.target.value)}
              style={inputStyle}
              disabled={!isAdmin}
            />
          </div>
        </div>
      </Card>

      <Card title="💰 부가 서비스 단가" style={{ marginTop: '1rem' }}>
        <p style={{ marginBottom: '1rem', color: '#666', fontSize: '0.9rem' }}>
          인보이스 계산 시 적용되는 부가 서비스 단가입니다. (단위: 원)
        </p>
        
        <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: '1rem' }}>
          <thead>
            <tr style={{ backgroundColor: '#f5f5f5' }}>
              <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>항목</th>
              <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd', width: '150px' }}>단가 (원)</th>
              {isAdmin && (
                <th style={{ padding: '0.75rem', textAlign: 'center', borderBottom: '2px solid #ddd', width: '120px' }}>작업</th>
              )}
            </tr>
          </thead>
          <tbody>
            {extraFees.map((item) => (
              <tr key={item.항목} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ padding: '0.75rem' }}>{item.항목}</td>
                <td style={{ padding: '0.75rem', textAlign: 'right' }}>
                  {isAdmin ? (
                    <input
                      type="number"
                      value={item.단가}
                      onChange={(e) => {
                        const newFees = extraFees.map((f) =>
                          f.항목 === item.항목 ? { ...f, 단가: parseInt(e.target.value) || 0 } : f
                        );
                        setExtraFees(newFees);
                      }}
                      onBlur={(e) => handleUpdateExtraFee(item.항목, parseInt(e.target.value) || 0)}
                      style={{
                        ...inputStyle,
                        width: '120px',
                        textAlign: 'right',
                      }}
                      disabled={savingFees}
                    />
                  ) : (
                    <span>{item.단가.toLocaleString()}원</span>
                  )}
                </td>
                {isAdmin && (
                  <td style={{ padding: '0.75rem', textAlign: 'center' }}>
                    <button
                      onClick={() => handleDeleteExtraFee(item.항목)}
                      disabled={savingFees}
                      style={{
                        padding: '0.25rem 0.5rem',
                        backgroundColor: '#ffebee',
                        color: '#c62828',
                        border: '1px solid #ffcdd2',
                        borderRadius: '4px',
                        cursor: savingFees ? 'not-allowed' : 'pointer',
                        fontSize: '0.85rem',
                      }}
                    >
                      삭제
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>

        {isAdmin && (
          <div style={{ 
            display: 'flex', 
            gap: '0.5rem', 
            alignItems: 'center',
            padding: '1rem',
            backgroundColor: '#f9f9f9',
            borderRadius: '4px',
          }}>
            <input
              type="text"
              value={newItemName}
              onChange={(e) => setNewItemName(e.target.value)}
              placeholder="새 항목명"
              style={{ ...inputStyle, flex: 1 }}
              disabled={savingFees}
            />
            <input
              type="number"
              value={newItemPrice}
              onChange={(e) => setNewItemPrice(parseInt(e.target.value) || 0)}
              placeholder="단가"
              style={{ ...inputStyle, width: '120px', textAlign: 'right' }}
              disabled={savingFees}
            />
            <button
              onClick={handleAddExtraFee}
              disabled={savingFees || !newItemName.trim()}
              style={{
                padding: '0.5rem 1rem',
                backgroundColor: savingFees || !newItemName.trim() ? '#ccc' : '#2196F3',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: savingFees || !newItemName.trim() ? 'not-allowed' : 'pointer',
              }}
            >
              + 추가
            </button>
          </div>
        )}
      </Card>

      {isAdmin && (
        <div style={{ marginTop: '1.5rem', textAlign: 'right' }}>
          <button
            onClick={handleSave}
            disabled={saving}
            style={{
              padding: '0.75rem 2rem',
              backgroundColor: saving ? '#ccc' : '#4CAF50',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              fontSize: '1rem',
              cursor: saving ? 'not-allowed' : 'pointer',
            }}
          >
            {saving ? '저장 중...' : '💾 설정 저장'}
          </button>
        </div>
      )}

      {settings.updated_at && (
        <p style={{ marginTop: '1rem', color: '#666', fontSize: '0.85rem' }}>
          마지막 수정: {settings.updated_at}
        </p>
      )}
    </div>
  );
}


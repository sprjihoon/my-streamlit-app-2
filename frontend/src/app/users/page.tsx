'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Card } from '@/components/Card';
import { Alert } from '@/components/Alert';
import { Loading } from '@/components/Loading';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const DEPARTMENTS = ['패션팀', '뷰티팀', '인사과', '경영지원'];
const POSITIONS = ['사원', '주임', '대리', '과장', '차장', '부장', '팀장', '인사과장', '대표'];

interface User {
  user_id: number;
  username: string;
  nickname: string;
  is_admin: boolean;
  department: string | null;
  position: string | null;
  join_date: string | null;
  naver_works_id: string | null;
  approver_id: number | null;
  leave_exempt: boolean;
}

interface ActorInfo {
  can_manage: boolean;
  is_admin: boolean;
  position: string;
  department: string;
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '0.5rem 0.75rem',
  border: '1px solid #ddd',
  borderRadius: '6px',
  fontSize: '0.9rem',
  boxSizing: 'border-box',
};

const labelStyle: React.CSSProperties = {
  display: 'block',
  marginBottom: '0.35rem',
  fontWeight: 600,
  fontSize: '0.85rem',
  color: '#444',
};

const DEPT_COLORS: Record<string, string> = {
  '패션팀': '#6366f1',
  '뷰티팀': '#ec4899',
  '인사과': '#10b981',
  '경영지원': '#f59e0b',
};

export default function UsersPage() {
  const router = useRouter();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [actorInfo, setActorInfo] = useState<ActorInfo | null>(null);

  // 새 사용자 폼
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    username: '',
    nickname: '',
    department: '',
    position: '사원',
    join_date: '',
    naver_works_id: '',
    approver_id: '',
    leave_exempt: false,
    is_admin: false,
  });

  // 수정 모달
  const [editUser, setEditUser] = useState<User | null>(null);
  const [editForm, setEditForm] = useState({
    nickname: '',
    password: '',
    department: '',
    position: '',
    join_date: '',
    naver_works_id: '',
    approver_id: '',
    leave_exempt: false,
    is_admin: false,
  });

  function getToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('token');
  }

  const loadUsers = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    try {
      setLoading(true);
      const res = await fetch(`${API_URL}/auth/users?token=${token}`);
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || '사용자 목록 로드 실패');
      }
      setUsers(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : '로드 실패');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const token = getToken();
    if (!token) { router.push('/login'); return; }

    fetch(`${API_URL}/auth/users/me/can-manage?token=${token}`)
      .then(r => r.json())
      .then((info: ActorInfo) => {
        setActorInfo(info);
        if (info.can_manage) {
          loadUsers();
        } else {
          setLoading(false);
          setError('사용자 관리 권한이 없습니다. (관리자/팀장/인사과장만 접근 가능)');
        }
      })
      .catch(() => router.push('/login'));
  }, [router, loadUsers]);

  function resetForm() {
    setForm({ username: '', nickname: '', department: actorInfo?.position === '팀장' ? (actorInfo.department || '') : '', position: '사원', join_date: '', naver_works_id: '', approver_id: '', leave_exempt: false, is_admin: false });
  }

  async function handleCreateUser(e: React.FormEvent) {
    e.preventDefault();
    const token = getToken();
    if (!token) return;

    if (!form.username.trim() || !form.nickname.trim() || !form.join_date) {
      setError('아이디, 성함, 입사일은 필수입니다.');
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const body: Record<string, unknown> = {
        username: form.username.trim(),
        nickname: form.nickname.trim(),
        department: form.department || null,
        position: form.position || null,
        join_date: form.join_date || null,
        naver_works_id: form.naver_works_id.trim() || null,
        approver_id: form.approver_id ? parseInt(form.approver_id) : null,
        leave_exempt: form.leave_exempt,
        is_admin: actorInfo?.is_admin ? form.is_admin : false,
      };

      const res = await fetch(`${API_URL}/auth/users?token=${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || '사용자 생성 실패');
      }

      const result = await res.json();
      setSuccess(result.message || '사용자가 생성되었습니다. 초기 비밀번호: 123456');
      setShowForm(false);
      resetForm();
      loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : '생성 실패');
    } finally {
      setSaving(false);
    }
  }

  function handleEditClick(user: User) {
    setEditUser(user);
    setEditForm({
      nickname: user.nickname,
      password: '',
      department: user.department || '',
      position: user.position || '',
      join_date: user.join_date || '',
      naver_works_id: user.naver_works_id || '',
      approver_id: user.approver_id ? String(user.approver_id) : '',
      leave_exempt: user.leave_exempt,
      is_admin: user.is_admin,
    });
  }

  async function handleUpdateUser() {
    const token = getToken();
    if (!token || !editUser) return;

    setSaving(true);
    setError(null);

    try {
      const updateData: Record<string, unknown> = {};
      if (editForm.nickname !== editUser.nickname) updateData.nickname = editForm.nickname;
      if (editForm.password.trim()) updateData.password = editForm.password.trim();
      if (editForm.department !== (editUser.department || '')) updateData.department = editForm.department;
      if (editForm.position !== (editUser.position || '')) updateData.position = editForm.position;
      if (editForm.join_date !== (editUser.join_date || '')) updateData.join_date = editForm.join_date;
      if (editForm.naver_works_id !== (editUser.naver_works_id || '')) updateData.naver_works_id = editForm.naver_works_id;
      if (editForm.approver_id !== (editUser.approver_id ? String(editUser.approver_id) : '')) {
        updateData.approver_id = editForm.approver_id ? parseInt(editForm.approver_id) : null;
      }
      if (editForm.leave_exempt !== editUser.leave_exempt) updateData.leave_exempt = editForm.leave_exempt;
      if (actorInfo?.is_admin && editForm.is_admin !== editUser.is_admin) updateData.is_admin = editForm.is_admin;

      if (Object.keys(updateData).length === 0) {
        setEditUser(null);
        return;
      }

      const res = await fetch(`${API_URL}/auth/users/${editUser.user_id}?token=${token}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updateData),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || '수정 실패');
      }

      setSuccess('사용자 정보가 수정되었습니다.');
      setEditUser(null);
      loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : '수정 실패');
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteUser(userId: number, username: string) {
    const token = getToken();
    if (!token) return;
    if (!confirm(`'${username}' 사용자를 삭제하시겠습니까?`)) return;

    try {
      const res = await fetch(`${API_URL}/auth/users/${userId}?token=${token}`, { method: 'DELETE' });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || '삭제 실패');
      }
      setSuccess('사용자가 삭제되었습니다.');
      loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : '삭제 실패');
    }
  }

  if (loading) return <Loading text="사용자 목록 로딩 중..." />;

  if (!actorInfo?.can_manage) {
    return (
      <div style={{ padding: '2rem', maxWidth: '800px', margin: '0 auto' }}>
        <Alert type="error" message="사용자 관리 권한이 없습니다. (관리자/팀장/인사과장만 접근 가능)" />
        <button onClick={() => router.push('/')} style={{ marginTop: '1rem', padding: '0.5rem 1rem', backgroundColor: '#2196F3', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
          홈으로 돌아가기
        </button>
      </div>
    );
  }

  const grouped = DEPARTMENTS.reduce<Record<string, User[]>>((acc, dept) => {
    acc[dept] = users.filter(u => u.department === dept);
    return acc;
  }, {});
  const ungrouped = users.filter(u => !u.department || !DEPARTMENTS.includes(u.department));

  return (
    <div style={{ padding: '2rem', maxWidth: '1100px', margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '2rem' }}>
        <h1 style={{ margin: 0 }}>👥 사용자 관리</h1>
        <button
          onClick={() => { setShowForm(!showForm); resetForm(); }}
          style={{ padding: '0.6rem 1.2rem', backgroundColor: showForm ? '#9e9e9e' : '#4CAF50', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 600 }}
        >
          {showForm ? '✕ 취소' : '➕ 직원 추가'}
        </button>
      </div>

      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}
      {success && <Alert type="success" message={success} onClose={() => setSuccess(null)} />}

      {/* 새 직원 등록 폼 */}
      {showForm && (
        <Card style={{ marginBottom: '1.5rem', border: '2px solid #4CAF50' }}>
          <h3 style={{ marginBottom: '1.25rem', color: '#2e7d32' }}>신규 직원 등록</h3>
          <p style={{ fontSize: '0.85rem', color: '#888', marginBottom: '1rem' }}>초기 비밀번호는 <strong>123456</strong>으로 설정되며, 첫 로그인 시 변경을 요구합니다.</p>
          <form onSubmit={handleCreateUser}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
              <div>
                <label style={labelStyle}>아이디 <span style={{ color: 'red' }}>*</span></label>
                <input style={inputStyle} type="text" value={form.username} onChange={e => setForm(f => ({ ...f, username: e.target.value }))} placeholder="로그인 아이디" />
              </div>
              <div>
                <label style={labelStyle}>성함 <span style={{ color: 'red' }}>*</span></label>
                <input style={inputStyle} type="text" value={form.nickname} onChange={e => setForm(f => ({ ...f, nickname: e.target.value }))} placeholder="실명" />
              </div>
              <div>
                <label style={labelStyle}>입사일 <span style={{ color: 'red' }}>*</span></label>
                <input style={inputStyle} type="date" value={form.join_date} onChange={e => setForm(f => ({ ...f, join_date: e.target.value }))} />
              </div>
              <div>
                <label style={labelStyle}>소속 팀</label>
                <select style={inputStyle} value={form.department} onChange={e => setForm(f => ({ ...f, department: e.target.value }))} disabled={actorInfo?.position === '팀장'}>
                  <option value="">선택...</option>
                  {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
                </select>
              </div>
              <div>
                <label style={labelStyle}>직급</label>
                <select style={inputStyle} value={form.position} onChange={e => setForm(f => ({ ...f, position: e.target.value }))}>
                  {POSITIONS.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div>
                <label style={labelStyle}>네이버웍스 ID</label>
                <input style={inputStyle} type="text" value={form.naver_works_id} onChange={e => setForm(f => ({ ...f, naver_works_id: e.target.value }))} placeholder="미입력 시 아이디와 동일" />
              </div>
            </div>

            <div style={{ display: 'flex', gap: '2rem', marginBottom: '1rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.9rem' }}>
                <input type="checkbox" checked={form.leave_exempt} onChange={e => setForm(f => ({ ...f, leave_exempt: e.target.checked }))} />
                연월차 관리 제외
              </label>
              {actorInfo?.is_admin && (
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.9rem' }}>
                  <input type="checkbox" checked={form.is_admin} onChange={e => setForm(f => ({ ...f, is_admin: e.target.checked }))} />
                  관리자 권한 부여
                </label>
              )}
            </div>

            <button type="submit" disabled={saving} style={{ padding: '0.6rem 1.5rem', backgroundColor: saving ? '#ccc' : '#4CAF50', color: 'white', border: 'none', borderRadius: '6px', cursor: saving ? 'not-allowed' : 'pointer', fontWeight: 600 }}>
              {saving ? '등록 중...' : '직원 등록'}
            </button>
          </form>
        </Card>
      )}

      {/* 팀별 사용자 목록 */}
      {[...DEPARTMENTS, '기타'].map(dept => {
        const list = dept === '기타' ? ungrouped : (grouped[dept] || []);
        if (list.length === 0) return null;
        const color = DEPT_COLORS[dept] || '#888';
        return (
          <Card key={dept} style={{ marginBottom: '1.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
              <span style={{ width: '12px', height: '12px', borderRadius: '50%', backgroundColor: color, display: 'inline-block' }} />
              <h3 style={{ margin: 0, color }}>{dept}</h3>
              <span style={{ fontSize: '0.8rem', color: '#999' }}>({list.length}명)</span>
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
              <thead>
                <tr style={{ backgroundColor: '#f8f9fa' }}>
                  {['성함', '아이디', '직급', '입사일', '네이버웍스ID', '연차제외', '권한', '작업'].map(h => (
                    <th key={h} style={{ padding: '0.6rem 0.75rem', textAlign: 'left', borderBottom: '2px solid #e0e0e0', fontWeight: 600, color: '#555', whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {list.map(user => (
                  <tr key={user.user_id} style={{ borderBottom: '1px solid #f0f0f0' }}>
                    <td style={{ padding: '0.6rem 0.75rem', fontWeight: 600 }}>{user.nickname}</td>
                    <td style={{ padding: '0.6rem 0.75rem', color: '#666' }}>{user.username}</td>
                    <td style={{ padding: '0.6rem 0.75rem' }}>
                      <span style={{ padding: '0.2rem 0.5rem', borderRadius: '4px', fontSize: '0.78rem', backgroundColor: `${color}20`, color }}>{user.position || '-'}</span>
                    </td>
                    <td style={{ padding: '0.6rem 0.75rem', color: '#666' }}>{user.join_date || '-'}</td>
                    <td style={{ padding: '0.6rem 0.75rem', color: '#666', fontSize: '0.85rem' }}>{user.naver_works_id || '-'}</td>
                    <td style={{ padding: '0.6rem 0.75rem', textAlign: 'center' }}>
                      {user.leave_exempt ? <span style={{ color: '#888', fontSize: '0.8rem' }}>제외</span> : <span style={{ color: '#4CAF50', fontSize: '0.8rem' }}>관리</span>}
                    </td>
                    <td style={{ padding: '0.6rem 0.75rem' }}>
                      <span style={{ padding: '0.2rem 0.5rem', borderRadius: '4px', fontSize: '0.78rem', backgroundColor: user.is_admin ? '#e3f2fd' : '#f5f5f5', color: user.is_admin ? '#1976d2' : '#666' }}>
                        {user.is_admin ? '관리자' : '일반'}
                      </span>
                    </td>
                    <td style={{ padding: '0.6rem 0.75rem' }}>
                      <button onClick={() => handleEditClick(user)} style={{ padding: '0.25rem 0.6rem', marginRight: '0.4rem', backgroundColor: '#ff9800', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '0.78rem' }}>수정</button>
                      {actorInfo?.is_admin && (
                        <button onClick={() => handleDeleteUser(user.user_id, user.username)} style={{ padding: '0.25rem 0.6rem', backgroundColor: '#f44336', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '0.78rem' }}>삭제</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        );
      })}

      {/* 수정 모달 */}
      {editUser && (
        <div
          style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}
          onClick={() => setEditUser(null)}
        >
          <div
            style={{ backgroundColor: 'white', borderRadius: '10px', padding: '2rem', width: '520px', maxWidth: '95vw', maxHeight: '90vh', overflowY: 'auto' }}
            onClick={e => e.stopPropagation()}
          >
            <h3 style={{ marginBottom: '1.25rem' }}>직원 정보 수정: <span style={{ color: '#4CAF50' }}>{editUser.nickname}</span></h3>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
              <div>
                <label style={labelStyle}>성함</label>
                <input style={inputStyle} type="text" value={editForm.nickname} onChange={e => setEditForm(f => ({ ...f, nickname: e.target.value }))} />
              </div>
              <div>
                <label style={labelStyle}>새 비밀번호 <span style={{ color: '#aaa', fontWeight: 400 }}>(변경 시만)</span></label>
                <input style={inputStyle} type="password" value={editForm.password} onChange={e => setEditForm(f => ({ ...f, password: e.target.value }))} placeholder="변경할 비밀번호" />
              </div>
              <div>
                <label style={labelStyle}>소속 팀</label>
                <select style={inputStyle} value={editForm.department} onChange={e => setEditForm(f => ({ ...f, department: e.target.value }))} disabled={actorInfo?.position === '팀장'}>
                  <option value="">선택...</option>
                  {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
                </select>
              </div>
              <div>
                <label style={labelStyle}>직급</label>
                <select style={inputStyle} value={editForm.position} onChange={e => setEditForm(f => ({ ...f, position: e.target.value }))}>
                  <option value="">선택...</option>
                  {POSITIONS.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div>
                <label style={labelStyle}>입사일</label>
                <input style={inputStyle} type="date" value={editForm.join_date} onChange={e => setEditForm(f => ({ ...f, join_date: e.target.value }))} />
              </div>
              <div>
                <label style={labelStyle}>네이버웍스 ID</label>
                <input style={inputStyle} type="text" value={editForm.naver_works_id} onChange={e => setEditForm(f => ({ ...f, naver_works_id: e.target.value }))} />
              </div>
            </div>

            <div style={{ display: 'flex', gap: '2rem', marginBottom: '1.5rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.9rem' }}>
                <input type="checkbox" checked={editForm.leave_exempt} onChange={e => setEditForm(f => ({ ...f, leave_exempt: e.target.checked }))} />
                연월차 관리 제외
              </label>
              {actorInfo?.is_admin && (
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.9rem' }}>
                  <input type="checkbox" checked={editForm.is_admin} onChange={e => setEditForm(f => ({ ...f, is_admin: e.target.checked }))} />
                  관리자 권한
                </label>
              )}
            </div>

            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button onClick={handleUpdateUser} disabled={saving} style={{ flex: 1, padding: '0.6rem', backgroundColor: saving ? '#ccc' : '#4CAF50', color: 'white', border: 'none', borderRadius: '6px', cursor: saving ? 'not-allowed' : 'pointer', fontWeight: 600 }}>
                {saving ? '저장 중...' : '저장'}
              </button>
              <button onClick={() => setEditUser(null)} style={{ flex: 1, padding: '0.6rem', backgroundColor: '#9e9e9e', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer' }}>
                취소
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

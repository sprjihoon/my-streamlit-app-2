'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Card } from '@/components/Card';
import { Alert } from '@/components/Alert';
import { Loading } from '@/components/Loading';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface User {
  user_id: number;
  username: string;
  nickname: string;
  is_admin: boolean;
}

export default function UsersPage() {
  const router = useRouter();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // 현재 사용자
  const [currentUser, setCurrentUser] = useState<User | null>(null);

  // 새 사용자 폼
  const [showForm, setShowForm] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newNickname, setNewNickname] = useState('');
  const [newIsAdmin, setNewIsAdmin] = useState(false);
  const [saving, setSaving] = useState(false);

  // 수정 모달
  const [editUser, setEditUser] = useState<User | null>(null);
  const [editNickname, setEditNickname] = useState('');
  const [editPassword, setEditPassword] = useState('');
  const [editIsAdmin, setEditIsAdmin] = useState(false);

  useEffect(() => {
    checkAuth();
  }, []);

  function getToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('token');
  }

  async function checkAuth() {
    const token = getToken();
    if (!token) {
      router.push('/login');
      return;
    }

    try {
      const res = await fetch(`${API_URL}/auth/me?token=${token}`);
      if (!res.ok) {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        router.push('/login');
        return;
      }

      const user = await res.json();
      setCurrentUser(user);

      if (!user.is_admin) {
        setError('관리자 권한이 필요합니다.');
        setLoading(false);
        return;
      }

      loadUsers();
    } catch {
      router.push('/login');
    }
  }

  async function loadUsers() {
    const token = getToken();
    if (!token) return;

    try {
      setLoading(true);
      const res = await fetch(`${API_URL}/auth/users?token=${token}`);
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || '사용자 목록 로드 실패');
      }
      const data = await res.json();
      setUsers(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : '로드 실패');
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateUser(e: React.FormEvent) {
    e.preventDefault();
    const token = getToken();
    if (!token) return;

    if (!newUsername.trim() || !newPassword.trim() || !newNickname.trim()) {
      setError('모든 필드를 입력하세요.');
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const res = await fetch(`${API_URL}/auth/users?token=${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: newUsername.trim(),
          password: newPassword.trim(),
          nickname: newNickname.trim(),
          is_admin: newIsAdmin,
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || '사용자 생성 실패');
      }

      setSuccess('사용자가 생성되었습니다.');
      setShowForm(false);
      setNewUsername('');
      setNewPassword('');
      setNewNickname('');
      setNewIsAdmin(false);
      loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : '생성 실패');
    } finally {
      setSaving(false);
    }
  }

  function handleEditClick(user: User) {
    setEditUser(user);
    setEditNickname(user.nickname);
    setEditPassword('');
    setEditIsAdmin(user.is_admin);
  }

  async function handleUpdateUser() {
    const token = getToken();
    if (!token || !editUser) return;

    setSaving(true);
    setError(null);

    try {
      const updateData: { nickname?: string; password?: string; is_admin?: boolean } = {};
      if (editNickname.trim() !== editUser.nickname) {
        updateData.nickname = editNickname.trim();
      }
      if (editPassword.trim()) {
        updateData.password = editPassword.trim();
      }
      if (editIsAdmin !== editUser.is_admin) {
        updateData.is_admin = editIsAdmin;
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
      const res = await fetch(`${API_URL}/auth/users/${userId}?token=${token}`, {
        method: 'DELETE',
      });

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

  if (loading) {
    return <Loading text="사용자 목록 로딩 중..." />;
  }

  if (!currentUser?.is_admin) {
    return (
      <div style={{ padding: '2rem', maxWidth: '800px', margin: '0 auto' }}>
        <Alert type="error" message="관리자 권한이 필요합니다." />
        <button
          onClick={() => router.push('/')}
          style={{
            marginTop: '1rem',
            padding: '0.5rem 1rem',
            backgroundColor: '#2196F3',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
          }}
        >
          홈으로 돌아가기
        </button>
      </div>
    );
  }

  return (
    <div style={{ padding: '2rem', maxWidth: '1000px', margin: '0 auto' }}>
      <h1 style={{ marginBottom: '2rem' }}>👥 사용자 관리</h1>

      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}
      {success && <Alert type="success" message={success} onClose={() => setSuccess(null)} />}

      {/* 새 사용자 추가 버튼 */}
      <div style={{ marginBottom: '1rem' }}>
        <button
          onClick={() => setShowForm(!showForm)}
          style={{
            padding: '0.5rem 1rem',
            backgroundColor: showForm ? '#9e9e9e' : '#4CAF50',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
          }}
        >
          {showForm ? '취소' : '➕ 새 사용자 추가'}
        </button>
      </div>

      {/* 새 사용자 폼 */}
      {showForm && (
        <Card style={{ marginBottom: '1rem' }}>
          <h3 style={{ marginBottom: '1rem' }}>새 사용자 등록</h3>
          <form onSubmit={handleCreateUser}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
              <div>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>아이디</label>
                <input
                  type="text"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  placeholder="로그인용 아이디"
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>비밀번호</label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="비밀번호"
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>닉네임</label>
                <input
                  type="text"
                  value={newNickname}
                  onChange={(e) => setNewNickname(e.target.value)}
                  placeholder="표시될 이름"
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>권한</label>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.5rem' }}>
                  <input
                    type="checkbox"
                    checked={newIsAdmin}
                    onChange={(e) => setNewIsAdmin(e.target.checked)}
                  />
                  관리자
                </label>
              </div>
            </div>
            <button
              type="submit"
              disabled={saving}
              style={{
                padding: '0.5rem 1rem',
                backgroundColor: saving ? '#ccc' : '#4CAF50',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: saving ? 'not-allowed' : 'pointer',
              }}
            >
              {saving ? '생성 중...' : '사용자 생성'}
            </button>
          </form>
        </Card>
      )}

      {/* 사용자 목록 */}
      <Card title="등록된 사용자">
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ backgroundColor: '#f5f5f5' }}>
              <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>ID</th>
              <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>아이디</th>
              <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>닉네임</th>
              <th style={{ padding: '0.75rem', textAlign: 'center', borderBottom: '2px solid #ddd' }}>권한</th>
              <th style={{ padding: '0.75rem', textAlign: 'center', borderBottom: '2px solid #ddd' }}>작업</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.user_id}>
                <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>{user.user_id}</td>
                <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>{user.username}</td>
                <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>{user.nickname}</td>
                <td style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '1px solid #eee' }}>
                  <span
                    style={{
                      padding: '0.25rem 0.5rem',
                      borderRadius: '4px',
                      fontSize: '0.75rem',
                      backgroundColor: user.is_admin ? '#e3f2fd' : '#f5f5f5',
                      color: user.is_admin ? '#1976d2' : '#666',
                    }}
                  >
                    {user.is_admin ? '관리자' : '일반'}
                  </span>
                </td>
                <td style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '1px solid #eee' }}>
                  <button
                    onClick={() => handleEditClick(user)}
                    style={{
                      padding: '0.25rem 0.5rem',
                      marginRight: '0.5rem',
                      backgroundColor: '#ff9800',
                      color: 'white',
                      border: 'none',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      fontSize: '0.75rem',
                    }}
                  >
                    수정
                  </button>
                  <button
                    onClick={() => handleDeleteUser(user.user_id, user.username)}
                    disabled={user.user_id === currentUser?.user_id}
                    style={{
                      padding: '0.25rem 0.5rem',
                      backgroundColor: user.user_id === currentUser?.user_id ? '#ccc' : '#f44336',
                      color: 'white',
                      border: 'none',
                      borderRadius: '4px',
                      cursor: user.user_id === currentUser?.user_id ? 'not-allowed' : 'pointer',
                      fontSize: '0.75rem',
                    }}
                  >
                    삭제
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* 수정 모달 */}
      {editUser && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setEditUser(null)}
        >
          <div
            style={{
              backgroundColor: 'white',
              borderRadius: '8px',
              padding: '2rem',
              width: '400px',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ marginBottom: '1rem' }}>사용자 수정: {editUser.username}</h3>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>닉네임</label>
              <input
                type="text"
                value={editNickname}
                onChange={(e) => setEditNickname(e.target.value)}
                style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
              />
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
                새 비밀번호 <span style={{ color: '#999', fontWeight: 'normal' }}>(변경 시에만 입력)</span>
              </label>
              <input
                type="password"
                value={editPassword}
                onChange={(e) => setEditPassword(e.target.value)}
                placeholder="변경할 비밀번호"
                style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
              />
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <input
                  type="checkbox"
                  checked={editIsAdmin}
                  onChange={(e) => setEditIsAdmin(e.target.checked)}
                />
                관리자 권한
              </label>
            </div>

            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                onClick={handleUpdateUser}
                disabled={saving}
                style={{
                  flex: 1,
                  padding: '0.5rem',
                  backgroundColor: saving ? '#ccc' : '#4CAF50',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: saving ? 'not-allowed' : 'pointer',
                }}
              >
                {saving ? '저장 중...' : '저장'}
              </button>
              <button
                onClick={() => setEditUser(null)}
                style={{
                  flex: 1,
                  padding: '0.5rem',
                  backgroundColor: '#9e9e9e',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                }}
              >
                취소
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


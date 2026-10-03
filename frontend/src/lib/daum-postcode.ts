type DaumPostcodeResult = {
  zonecode: string;
  roadAddress: string;
  jibunAddress: string;
};

export type PickedAddress = {
  zip: string;
  addr1: string;
};

declare global {
  interface Window {
    daum?: {
      Postcode: new (opts: {
        oncomplete: (data: DaumPostcodeResult) => void;
      }) => { open: () => void };
    };
  }
}

const SCRIPT_SRC = 'https://t1.daumcdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js';

let loading: Promise<void> | null = null;

function loadDaumPostcode(): Promise<void> {
  if (typeof window === 'undefined') {
    return Promise.reject(new Error('주소 검색을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.'));
  }
  if (window.daum?.Postcode) return Promise.resolve();
  if (!loading) {
    loading = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = SCRIPT_SRC;
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => {
        loading = null;
        reject(new Error('주소 검색을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.'));
      };
      document.body.appendChild(script);
    });
  }
  return loading;
}

export async function openDaumPostcode(onPick: (picked: PickedAddress) => void): Promise<void> {
  await loadDaumPostcode();
  if (!window.daum?.Postcode) {
    throw new Error('주소 검색을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.');
  }
  new window.daum.Postcode({
    oncomplete(data) {
      const addr1 = data.roadAddress || data.jibunAddress;
      if (!data.zonecode || !addr1) return;
      onPick({ zip: data.zonecode, addr1 });
    },
  }).open();
}

// EMS 인보이스 품목 카탈로그 (HS코드 6자리 기준)
export interface ItemCategory {
  id: string;
  name_ko: string;    // 한국어 표시명
  name_en: string;    // 영문 인보이스명
  hs_code: string;    // 6자리 HS코드
  group: string;      // 그룹명
  origin_country?: string;
  saved?: boolean;
  saved_id?: number;
  label?: string;
}

export const ITEM_CATEGORIES: ItemCategory[] = [
  // ── 유학생 짐 ──
  // 630900(worn clothing in bulk)은 상업용 묶음 코드라 개인짐에 부적합 → 품목별 정확한 코드 사용
  { id: "student_clothing",    name_ko: "의류 (사용)",               name_en: "Used Clothing",                 hs_code: "610910", group: "유학생 짐" },
  { id: "student_shoes",       name_ko: "신발 (사용)",               name_en: "Used Footwear",                 hs_code: "640299", group: "유학생 짐" },
  { id: "student_bag",         name_ko: "가방·백팩 (사용)",          name_en: "Used Bag / Backpack",           hs_code: "420292", group: "유학생 짐" },
  { id: "student_bedding",     name_ko: "침구·이불·베개",            name_en: "Bedding / Blanket / Pillow",    hs_code: "940490", group: "유학생 짐" },
  { id: "student_books",       name_ko: "교재·서적",                 name_en: "Textbooks / Books",             hs_code: "490199", group: "유학생 짐" },
  { id: "student_stationery",  name_ko: "학용품·문구",               name_en: "Stationery / School Supplies",  hs_code: "482010", group: "유학생 짐" },
  { id: "student_laptop",      name_ko: "노트북 (사용)",             name_en: "Used Laptop / Notebook",        hs_code: "847130", group: "유학생 짐" },
  { id: "student_tablet",      name_ko: "태블릿 (사용)",             name_en: "Used Tablet",                   hs_code: "847130", group: "유학생 짐" },
  { id: "student_earphone",    name_ko: "이어폰·헤드폰 (사용)",      name_en: "Used Earphones / Headphones",   hs_code: "851830", group: "유학생 짐" },
  { id: "student_kitchen",     name_ko: "주방용품 (사용)",           name_en: "Used Kitchen Items",            hs_code: "392410", group: "유학생 짐" },
  { id: "student_toiletries",  name_ko: "세면·위생용품",             name_en: "Personal Care / Toiletries",    hs_code: "330499", group: "유학생 짐" },
  { id: "student_sports",      name_ko: "운동·스포츠용품 (사용)",    name_en: "Used Sports Equipment",         hs_code: "950699", group: "유학생 짐" },
  { id: "student_misc",        name_ko: "기타 잡화 (사용)",          name_en: "Used Miscellaneous Goods",      hs_code: "392690", group: "유학생 짐" },

  // ── 의류 ──
  { id: "clothing_top",     name_ko: "상의 (티셔츠·셔츠·블라우스)", name_en: "Clothing - Top",          hs_code: "610910", group: "의류" },
  { id: "clothing_bottom",  name_ko: "하의 (바지·스커트·레깅스)",   name_en: "Clothing - Bottom",       hs_code: "610462", group: "의류" },
  { id: "clothing_dress",   name_ko: "원피스·드레스",               name_en: "Dress",                   hs_code: "610441", group: "의류" },
  { id: "clothing_outer",   name_ko: "아우터 (코트·자켓·패딩)",     name_en: "Outerwear / Jacket",      hs_code: "620111", group: "의류" },
  { id: "clothing_sports",  name_ko: "스포츠·운동복",               name_en: "Sportswear",              hs_code: "611120", group: "의류" },
  { id: "clothing_underwear", name_ko: "속옷·양말",                 name_en: "Underwear / Socks",       hs_code: "621210", group: "의류" },
  { id: "clothing_baby",    name_ko: "유아·아동 의류",              name_en: "Baby / Children Clothing",hs_code: "611120", group: "의류" },
  { id: "clothing_school_uniform", name_ko: "교복·유니폼",          name_en: "Uniform",                 hs_code: "610910", group: "의류" },

  // ── 신발 ──
  { id: "shoes_sneakers",   name_ko: "운동화·스니커즈",             name_en: "Sneakers / Athletic Shoes", hs_code: "640411", group: "신발" },
  { id: "shoes_leather",    name_ko: "가죽 구두·로퍼",             name_en: "Leather Shoes / Loafers",  hs_code: "640351", group: "신발" },
  { id: "shoes_sandals",    name_ko: "샌들·슬리퍼",               name_en: "Sandals / Slippers",       hs_code: "640219", group: "신발" },
  { id: "shoes_boots",      name_ko: "부츠",                       name_en: "Boots",                   hs_code: "640320", group: "신발" },

  // ── 가방·잡화 ──
  { id: "bag_handbag",      name_ko: "핸드백",                     name_en: "Handbag",                 hs_code: "420222", group: "가방·잡화" },
  { id: "bag_backpack",     name_ko: "백팩·배낭",                  name_en: "Backpack",                hs_code: "420292", group: "가방·잡화" },
  { id: "bag_wallet",       name_ko: "지갑",                       name_en: "Wallet / Purse",          hs_code: "420232", group: "가방·잡화" },
  { id: "bag_luggage",      name_ko: "여행용 가방·트렁크",         name_en: "Suitcase / Luggage",      hs_code: "420211", group: "가방·잡화" },
  { id: "bag_belt",         name_ko: "벨트",                       name_en: "Belt",                    hs_code: "420600", group: "가방·잡화" },

  // ── 화장품·미용 ──
  { id: "cosmetics_skincare", name_ko: "스킨케어 (크림·로션·세럼)", name_en: "Skincare (Cream/Lotion)", hs_code: "330499", group: "화장품·미용" },
  { id: "cosmetics_makeup",   name_ko: "색조 화장품 (립·아이섀도)", name_en: "Makeup (Lip/Eyeshadow)", hs_code: "330420", group: "화장품·미용" },
  { id: "cosmetics_perfume",  name_ko: "향수",                     name_en: "Perfume / Cologne",       hs_code: "330300", group: "화장품·미용" },
  { id: "cosmetics_haircare", name_ko: "헤어케어 (샴푸·트리트먼트)", name_en: "Hair Care Products",   hs_code: "330511", group: "화장품·미용" },
  { id: "cosmetics_sunscreen", name_ko: "선크림·자외선차단제",      name_en: "Sunscreen",              hs_code: "330410", group: "화장품·미용" },

  // ── 전자기기 ──
  { id: "electronics_phone",   name_ko: "스마트폰",               name_en: "Smartphone",              hs_code: "851712", group: "전자기기" },
  { id: "electronics_laptop",  name_ko: "노트북·랩탑",            name_en: "Laptop / Notebook",       hs_code: "847130", group: "전자기기" },
  { id: "electronics_tablet",  name_ko: "태블릿·패드",            name_en: "Tablet",                  hs_code: "847130", group: "전자기기" },
  { id: "electronics_earphone", name_ko: "이어폰·헤드폰",         name_en: "Earphones / Headphones",  hs_code: "851830", group: "전자기기" },
  { id: "electronics_watch",   name_ko: "스마트워치",             name_en: "Smartwatch",              hs_code: "910210", group: "전자기기" },
  { id: "electronics_camera",  name_ko: "카메라",                 name_en: "Camera",                  hs_code: "900640", group: "전자기기" },
  { id: "electronics_charger", name_ko: "충전기·케이블·어댑터",   name_en: "Charger / Cable / Adapter", hs_code: "850440", group: "전자기기" },
  { id: "electronics_game",    name_ko: "게임기·콘솔",            name_en: "Game Console",            hs_code: "950450", group: "전자기기" },

  // ── 시계·주얼리 ──
  { id: "watch_analog",     name_ko: "손목시계 (아날로그)",        name_en: "Wristwatch",              hs_code: "910210", group: "시계·주얼리" },
  { id: "jewelry_necklace", name_ko: "목걸이·팔찌·반지",          name_en: "Necklace / Bracelet / Ring", hs_code: "711319", group: "시계·주얼리" },
  { id: "jewelry_costume",  name_ko: "패션 액세서리 (이미테이션)", name_en: "Fashion Jewelry / Accessories", hs_code: "711790", group: "시계·주얼리" },

  // ── 도서·문구 ──
  { id: "books",            name_ko: "책·서적",                    name_en: "Books",                   hs_code: "490199", group: "도서·문구" },
  { id: "stationery",       name_ko: "문구류 (노트·펜·다이어리)",  name_en: "Stationery / Notebooks",  hs_code: "482010", group: "도서·문구" },

  // ── 스포츠·취미 ──
  { id: "sports_equipment", name_ko: "스포츠용품 (라켓·클럽 등)", name_en: "Sports Equipment",        hs_code: "950699", group: "스포츠·취미" },
  { id: "sports_mat",       name_ko: "요가매트·운동 매트",         name_en: "Exercise Mat",            hs_code: "950691", group: "스포츠·취미" },
  { id: "toys_general",     name_ko: "장난감·완구",               name_en: "Toys",                    hs_code: "950399", group: "스포츠·취미" },
  { id: "hobby_craft",      name_ko: "취미용품 (그림·공예)",       name_en: "Hobby / Craft Supplies",  hs_code: "950340", group: "스포츠·취미" },

  // ── 홈·생활 ──
  { id: "home_bedding",     name_ko: "침구류 (이불·베개·시트)",    name_en: "Bedding / Blanket / Pillow", hs_code: "940490", group: "홈·생활" },
  { id: "home_kitchen",     name_ko: "주방용품",                   name_en: "Kitchen Goods",           hs_code: "392410", group: "홈·생활" },
  { id: "home_decor",       name_ko: "인테리어·홈데코",            name_en: "Home Decor",              hs_code: "442090", group: "홈·생활" },
  { id: "home_cleaning",    name_ko: "청소·생활용품",              name_en: "Household Goods",         hs_code: "340290", group: "홈·생활" },

  // ── 건강·식품 ──
  { id: "health_supplement", name_ko: "건강식품·영양제",              name_en: "Health Supplements / Vitamins", hs_code: "210690", group: "건강·식품" },
  { id: "health_medicine",   name_ko: "의약품·의약외품",              name_en: "Medicine / Pharmaceutical",     hs_code: "300490", group: "건강·식품" },
  { id: "food_kimchi",       name_ko: "김치",                        name_en: "Kimchi (Fermented Vegetables)",  hs_code: "200980", group: "건강·식품" },
  { id: "food_ramen",        name_ko: "라면·인스턴트 식품",            name_en: "Ramen / Instant Noodles",       hs_code: "190230", group: "건강·식품" },
  { id: "food_snacks",       name_ko: "과자·스낵",                   name_en: "Snacks / Crackers",             hs_code: "190590", group: "건강·식품" },
  { id: "food_sauce",        name_ko: "소스·조미료·고추장·된장",       name_en: "Sauce / Seasoning / Paste",     hs_code: "210390", group: "건강·식품" },
  { id: "food_rice",         name_ko: "쌀·잡곡·곡류",                name_en: "Rice / Grains / Cereals",       hs_code: "100630", group: "건강·식품" },
  { id: "food_seaweed",      name_ko: "김·미역·해조류",               name_en: "Seaweed / Dried Kelp",          hs_code: "121221", group: "건강·식품" },
  { id: "food_dried_seafood", name_ko: "건어물·건새우·오징어포",       name_en: "Dried Seafood",                 hs_code: "030559", group: "건강·식품" },
  { id: "food_tea",          name_ko: "차·한방차·커피",               name_en: "Tea / Herbal Tea / Coffee",     hs_code: "090240", group: "건강·식품" },
  { id: "food_candy",        name_ko: "사탕·초콜릿·젤리",             name_en: "Candy / Chocolate / Jelly",     hs_code: "170490", group: "건강·식품" },
  { id: "food_bev",          name_ko: "음료·주스·이온음료",            name_en: "Beverages / Juice",             hs_code: "220290", group: "건강·식품" },
  { id: "food_alcohol",      name_ko: "주류 (소주·막걸리·맥주)",       name_en: "Alcoholic Beverages (Soju/Beer)", hs_code: "220600", group: "건강·식품" },

  // ── 기타 ──
  { id: "musical_instrument", name_ko: "악기",                    name_en: "Musical Instrument",      hs_code: "920599", group: "기타" },
  { id: "art_supplies",       name_ko: "미술용품·화구",            name_en: "Art Supplies",            hs_code: "321310", group: "기타" },
  { id: "other",              name_ko: "기타",                    name_en: "Other Goods",             hs_code: "",       group: "기타" },
];

export const ITEM_GROUPS = Array.from(new Set(ITEM_CATEGORIES.map((c) => c.group)));

export function searchItemCategories(query: string, extra: ItemCategory[] = []) {
  const source = extra.length ? [...extra, ...ITEM_CATEGORIES] : ITEM_CATEGORIES;
  const seen = new Set<string>();
  const unique: ItemCategory[] = [];
  for (const c of source) {
    const key = `${c.hs_code}|${c.name_en.toLowerCase()}|${c.id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(c);
  }
  const q = query.trim().toLowerCase();
  if (!q) return unique;
  const digits = q.replace(/\s+/g, "");
  return unique.filter(
    (c) =>
      c.name_ko.toLowerCase().includes(q) ||
      c.name_en.toLowerCase().includes(q) ||
      (c.label || "").toLowerCase().includes(q) ||
      c.hs_code.includes(digits) ||
      (c.id || "").toLowerCase().includes(q)
  );
}

export type AddressComponent = {
  long_name: string;
  short_name: string;
  types: string[];
};

export type PlaceLike = {
  address_components?: AddressComponent[];
  formatted_address?: string;
};

type PlacesAutocomplete = {
  addListener: (event: string, handler: () => void) => void;
  getPlace: () => PlaceLike;
  setComponentRestrictions: (opts: { country: string }) => void;
};

declare global {
  interface Window {
    google?: {
      maps: {
        places: {
          Autocomplete: new (
            input: HTMLInputElement,
            opts: {
              types?: string[];
              componentRestrictions?: { country: string };
              fields?: string[];
            }
          ) => PlacesAutocomplete;
        };
      };
    };
  }
}

let scriptLoadPromise: Promise<void> | null = null;

export function googleMapsApiKey(): string {
  return (process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? "").replace(/[\r\n]/g, "").trim();
}

export function loadGoogleMapsScript(apiKey: string): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.google?.maps?.places) return Promise.resolve();
  if (!apiKey) return Promise.reject(new Error("Google Maps API key missing"));
  if (scriptLoadPromise) return scriptLoadPromise;

  scriptLoadPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector("script[data-gmaps]") as HTMLScriptElement | null;
    if (existing) {
      if (window.google?.maps?.places) {
        resolve();
        return;
      }
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => {
        scriptLoadPromise = null;
        reject(new Error("Failed to load Google Maps API"));
      });
      return;
    }
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&libraries=places&loading=async`;
    script.async = true;
    script.defer = true;
    script.dataset.gmaps = "1";
    script.onload = () => {
      const started = Date.now();
      const wait = () => {
        if (window.google?.maps?.places) {
          resolve();
          return;
        }
        if (Date.now() - started > 8000) {
          scriptLoadPromise = null;
          reject(new Error("Google Places library not ready"));
          return;
        }
        window.setTimeout(wait, 50);
      };
      wait();
    };
    script.onerror = () => {
      scriptLoadPromise = null;
      reject(new Error("Failed to load Google Maps API"));
    };
    document.head.appendChild(script);
  });

  return scriptLoadPromise;
}

export interface ParsedPlace {
  addr3: string;
  addr2: string;
  addr1: string;
  zip: string;
}

export function parsePlaceResult(place: PlaceLike, countryCode: string): ParsedPlace {
  const components = place.address_components ?? [];
  const get = (type: string) => components.find((c) => c.types.includes(type))?.long_name ?? "";
  const getShort = (type: string) => components.find((c) => c.types.includes(type))?.short_name ?? "";

  const streetNumber = get("street_number");
  const route = get("route");
  const sublocality2 = get("sublocality_level_2");
  const sublocality1 = get("sublocality_level_1");
  const locality = get("locality");
  const adminArea1 = get("administrative_area_level_1");
  const adminArea1Short = getShort("administrative_area_level_1");
  const postalCode = get("postal_code");

  let addr3 = "";
  let addr2 = "";
  let addr1 = "";
  const country = countryCode.toUpperCase();

  if (country === "JP") {
    addr3 = [sublocality2, streetNumber].filter(Boolean).join("-") ||
      [route, streetNumber].filter(Boolean).join(" ") ||
      sublocality1;
    addr2 = sublocality1 || locality;
    addr1 = adminArea1;
  } else if (["US", "CA", "AU", "GB", "NZ"].includes(country)) {
    addr3 = [streetNumber, route].filter(Boolean).join(" ");
    addr2 = locality;
    addr1 = adminArea1Short || adminArea1;
  } else {
    addr3 = [streetNumber, route].filter(Boolean).join(" ") || sublocality1;
    addr2 = sublocality1 || locality;
    addr1 = adminArea1;
  }

  if (!addr3 && place.formatted_address) {
    addr3 = place.formatted_address.split(",")[0].trim();
  }

  return { addr3, addr2, addr1, zip: postalCode };
}

export interface AddressValidationResult {
  suggestedAddr3: string;
  suggestedAddr2: string;
  suggestedAddr1: string;
  suggestedZip: string;
  formattedAddress: string;
  isSame: boolean;
}

const ADDRESS_VALIDATION_SUPPORTED = new Set([
  "AR", "AT", "AU", "BE", "BG", "BR", "CA", "CH", "CL", "CO", "CZ", "DE", "DK",
  "EE", "ES", "FI", "FR", "GB", "HR", "HU", "IE", "IN", "IT", "JP", "LT", "LU",
  "LV", "MX", "MY", "NL", "NO", "NZ", "PL", "PR", "PT", "SE", "SG", "SI", "SK", "US",
]);

export function supportsAddressValidation(countryCode: string): boolean {
  return ADDRESS_VALIDATION_SUPPORTED.has(countryCode.toUpperCase());
}

export async function validateAddressWithGoogle(
  apiKey: string,
  addr: { addr3: string; addr2: string; addr1: string; zip: string; countryCode: string }
): Promise<AddressValidationResult | null> {
  try {
    const addressLines = [addr.addr3, addr.addr2, addr.addr1, addr.zip].filter(Boolean);
    if (!addressLines.length) return null;
    const res = await fetch(
      `https://addressvalidation.googleapis.com/v1:validateAddress?key=${encodeURIComponent(apiKey)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          address: {
            regionCode: addr.countryCode,
            addressLines,
          },
        }),
      }
    );
    if (!res.ok) return null;
    const data = await res.json();
    const result = data?.result;
    if (!result?.address) return null;
    const postalAddr = result.address.postalAddress ?? {};
    const lines: string[] = (postalAddr.addressLines ?? []).map((line: string) => String(line || '').trim()).filter(Boolean);
    const components: Array<{ componentType?: string; componentName?: { text?: string } | string }> =
      result.address.addressComponents ?? [];
    const componentText = (type: string) => {
      const found = components.find((c) => c.componentType === type);
      const name = found?.componentName;
      if (!name) return '';
      if (typeof name === 'string') return name.trim();
      return (name.text || '').trim();
    };
    const suggestedAddr3 = lines.join(', ');
    const suggestedAddr2: string = (postalAddr.locality ?? '').trim() || componentText('postal_town') || componentText('locality');
    const suggestedAddr1: string = (postalAddr.administrativeArea ?? '').trim() || componentText('administrative_area_level_1');
    const suggestedZip: string = postalAddr.postalCode ?? '';
    const formattedAddress: string = result.address.formattedAddress ?? "";
    const normalize = (s: string) => s.trim().toLowerCase().replace(/\s+/g, " ");
    const isSame =
      normalize(suggestedAddr3) === normalize(addr.addr3) &&
      normalize(suggestedAddr2) === normalize(addr.addr2) &&
      normalize(suggestedAddr1) === normalize(addr.addr1) &&
      normalize(suggestedZip) === normalize(addr.zip);
    return { suggestedAddr3, suggestedAddr2, suggestedAddr1, suggestedZip, formattedAddress, isSame };
  } catch {
    return null;
  }
}

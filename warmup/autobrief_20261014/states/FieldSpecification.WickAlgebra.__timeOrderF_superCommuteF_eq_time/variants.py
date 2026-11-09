import json
s=open('saved.lean').read()
v=[]
v.append({'label':'direct-noinsert-rw','content':s.replace('    have h := s []\n    simp only [List.nil_append, ofCrAnListF_nil, mul_one] at h\n    rw [← h]','    simpa only [List.nil_append, ofCrAnListF_nil, mul_one] using s []')})
v.append({'label':'simp-at-tail','content':s.replace('    have h := s []\n    simp only [List.nil_append, ofCrAnListF_nil, mul_one] at h\n    rw [← h]','    have h := s []\n    simp only [List.nil_append, ofCrAnListF_nil, mul_one] at h\n    simp only [← h]')})
v.append({'label':'erw-list-nil','content':s.replace('    have h := s []\n    simp only [List.nil_append, ofCrAnListF_nil, mul_one] at h\n    rw [← h]','    have h := s []\n    rw [ofCrAnListF_nil, mul_one] at h\n    rw [← h]')})
v.append({'label':'dsimp-only','content':s.replace('  dsimp [T, C, M]','  dsimp only [T, C, M, LinearMap.comp_apply, LinearMap.compr₂_apply, LinearMap.mul_apply, LinearMap.mulRight_apply, LinearMap.mulLeft_apply, AlgHom.toLinearMap_apply]')})
json.dump({'variants':v},open('variants.json','w'))
